import mimetypes
import os
import tempfile
import uuid
import re
from urllib.parse import quote
from typing import Iterator
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, joinedload
from app.api.common import ensure_owner_or_moderator, get_visible_video, serialize_video, serialize_videos
from app.core.config import settings
from app.core.dependencies import get_current_user, require_user
from app.db import get_db
from app.models import Comment, Like, Report, User, Video, VideoAccess
from app.schemas import AccessGrantCreate, CommentCreate, ReportCreate
from app.services.storage import delete_object, get_object, head_object, upload_file
from app.services.jobs import enqueue_video_processing

router = APIRouter(prefix="/api", tags=["Видео"])


def _parse_range(value: str, total: int) -> tuple[int, int]:
    try:
        unit, spec = value.split("=", 1)
        if unit.strip() != "bytes" or "," in spec:
            raise ValueError
        first, last = spec.split("-", 1)
        if not first:
            length = int(last)
            start, end = max(0, total - length), total - 1
        else:
            start = int(first)
            end = int(last) if last else total - 1
        if start < 0 or end < start or start >= total:
            raise ValueError
        return start, min(end, total - 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=416, detail="Некорректный диапазон байтов", headers={"Content-Range": f"bytes */{total}"})


def _stream_from_s3(key: str, byte_range: str | None = None) -> tuple[Iterator[bytes], dict]:
    obj = get_object(key, byte_range)
    body = obj["Body"]
    def iterator():
        try:
            while True:
                chunk = body.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()
    return iterator(), obj


@router.get("/videos")
def list_videos(
    sort: str = Query(default="recent", pattern="^(recent|popular)$"),
    limit: int = Query(default=24, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user),
):
    query = db.query(Video).options(joinedload(Video.owner)).filter(
        Video.visibility == "public", Video.status == "ready", Video.is_hidden.is_(False)
    )
    if sort == "popular":
        query = query.order_by(desc(Video.views), desc(Video.created_at))
    else:
        query = query.order_by(desc(Video.created_at))
    videos = query.offset(offset).limit(limit).all()
    return {"items": serialize_videos(db, videos, viewer), "limit": limit, "offset": offset}


@router.get("/me/videos")
def list_my_videos(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Return the signed-in user's published videos, including private videos they own."""
    videos = db.query(Video).options(joinedload(Video.owner)).filter(
        Video.owner_id == user.id,
        Video.status == "ready",
        Video.is_hidden.is_(False),
    ).order_by(desc(Video.created_at)).limit(100).all()
    return {"items": serialize_videos(db, videos, user)}


@router.get("/me/liked")
def list_liked_videos(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Return videos liked by the signed-in user that are still visible to them."""
    videos = db.query(Video).join(Like, Like.video_id == Video.id).options(
        joinedload(Video.owner)
    ).filter(
        Like.user_id == user.id,
        Video.status == "ready",
        Video.is_hidden.is_(False),
        or_(Video.visibility == "public", Video.owner_id == user.id, VideoAccess.user_id == user.id),
    ).outerjoin(VideoAccess, VideoAccess.video_id == Video.id).distinct().order_by(desc(Like.created_at)).limit(100).all()
    return {"items": serialize_videos(db, videos, user)}


@router.get("/search")
def search_videos(q: str = Query(min_length=1, max_length=120), limit: int = Query(default=30, ge=1, le=60), db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user)):
    term = f"%{q.strip()}%"
    query = db.query(Video).options(joinedload(Video.owner)).filter(
        Video.status == "ready", Video.is_hidden.is_(False),
        or_(Video.visibility == "public", Video.owner_id == (viewer.id if viewer else -1)),
        or_(Video.title.ilike(term), Video.description.ilike(term)),
    ).order_by(desc(Video.created_at)).limit(limit)
    return {"query": q, "items": serialize_videos(db, query.all(), viewer)}


@router.post("/videos/upload", status_code=status.HTTP_201_CREATED)
def upload_video(
    title: str = Form(min_length=1, max_length=120),
    description: str = Form(default="", max_length=10000),
    visibility: str = Form(default="public", pattern="^(public|private)$"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    filename = file.filename or "video.mp4"
    extension = os.path.splitext(filename)[1].lower()
    if extension not in settings.allowed_extensions:
        raise HTTPException(status_code=415, detail=f"Формат не поддерживается. Допустимо: {', '.join(sorted(settings.allowed_extensions))}")
    header = file.file.read(16)
    file.file.seek(0)
    if extension in {".mp4", ".mov"} and (len(header) < 8 or header[4:8] != b"ftyp"):
        raise HTTPException(status_code=415, detail="Содержимое файла не похоже на MP4/MOV")
    if extension in {".mkv", ".webm"} and header[:4] != bytes.fromhex("1a45dfa3"):
        raise HTTPException(status_code=415, detail="Содержимое файла не похоже на MKV/WEBM")
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="Название видео не может быть пустым")
    temp_path = None
    stored_key = None
    size = 0
    try:
        with tempfile.NamedTemporaryFile(prefix="streamhub-upload-", delete=False) as temp:
            temp_path = temp.name
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Файл превышает допустимый размер")
                temp.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Загружен пустой файл")
        key = f"originals/{user.id}/{uuid.uuid4().hex}{extension}"
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        upload_file(temp_path, key, mime)
        stored_key = key
        video = Video(owner_id=user.id, title=clean_title, description=description, visibility=visibility, status="processing", original_key=key)
        db.add(video)
        db.commit()
        db.refresh(video)
        queued = True
        try:
            enqueue_video_processing(video.id)
        except Exception as exc:
            queued = False
            video.status = "failed"
            video.processing_error = "Не удалось поставить задачу обработки в очередь: " + str(exc)[:300]
            db.commit()
        message = "Видео загружено и поставлено в очередь обработки" if queued else "Видео сохранено, но не удалось запустить обработку"
        return {"video": serialize_video(db, video, user), "message": message}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        if stored_key:
            try:
                delete_object(stored_key)
            except Exception:
                pass
        raise HTTPException(status_code=502, detail="Не удалось сохранить видео в объектное хранилище")
    finally:
        file.file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.get("/videos/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user)):
    video = get_visible_video(db, video_id, viewer)
    return serialize_video(db, video, viewer)


@router.get("/videos/{video_id}/stream")
def stream_video(video_id: int, request: Request, range_header: str | None = Header(default=None, alias="Range"), db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user)):
    video = get_visible_video(db, video_id, viewer)
    if video.status != "ready" or not video.processed_key:
        raise HTTPException(status_code=409, detail="Видео ещё обрабатывается")
    try:
        head = head_object(video.processed_key)
        total = head["ContentLength"]
        start = end = None
        range_value = None
        if range_header:
            start, end = _parse_range(range_header, total)
            range_value = f"bytes={start}-{end}"
        iterator, obj = _stream_from_s3(video.processed_key, range_value)
        headers = {"Accept-Ranges": "bytes", "Content-Length": str(obj.get("ContentLength", total)), "Cache-Control": "private, max-age=60"}
        status_code = 200
        if range_value:
            headers["Content-Range"] = f"bytes {start}-{end}/{total}"
            status_code = 206
        if not range_header or start == 0:
            video.views += 1
            db.commit()
        return StreamingResponse(iterator, status_code=status_code, media_type="video/mp4", headers=headers)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Не удалось получить видео из хранилища")


@router.get("/videos/{video_id}/thumbnail")
def thumbnail(video_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user)):
    video = get_visible_video(db, video_id, viewer)
    if not video.thumbnail_key:
        raise HTTPException(status_code=404, detail="Превью ещё не готово")
    try:
        iterator, obj = _stream_from_s3(video.thumbnail_key)
        return StreamingResponse(iterator, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300", "Content-Length": str(obj["ContentLength"])})
    except Exception:
        raise HTTPException(status_code=502, detail="Не удалось получить превью")


@router.get("/videos/{video_id}/download")
def download_video(video_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user)):
    """Stream a downloadable MP4 while enforcing the same visibility rules as playback."""
    video = get_visible_video(db, video_id, viewer)
    if video.status != "ready" or not video.processed_key:
        raise HTTPException(status_code=409, detail="Видео ещё не готово к скачиванию")
    try:
        head = head_object(video.processed_key)
        iterator, obj = _stream_from_s3(video.processed_key)
        safe_title = re.sub(r"[\\/\r\n\";]+", "_", video.title).strip(" ._") or f"video-{video.id}"
        filename = f"{safe_title}.mp4"
        headers = {
            "Content-Length": str(obj.get("ContentLength", head.get("ContentLength", 0))),
            "Content-Disposition": f"attachment; filename=\"streamhub-video-{video.id}.mp4\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store",
        }
        return StreamingResponse(iterator, media_type="video/mp4", headers=headers)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Не удалось подготовить видео к скачиванию")


@router.post("/videos/{video_id}/like")
def toggle_like(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = get_visible_video(db, video_id, user)
    existing = db.query(Like).filter_by(video_id=video.id, user_id=user.id).first()
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(Like(video_id=video.id, user_id=user.id))
        liked = True
    db.commit()
    count = db.query(func.count(Like.id)).filter_by(video_id=video.id).scalar() or 0
    return {"liked": liked, "like_count": count}


@router.get("/videos/{video_id}/comments")
def list_comments(video_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user)):
    video = get_visible_video(db, video_id, viewer)
    comments = db.query(Comment).options(joinedload(Comment.user)).filter_by(video_id=video.id).order_by(Comment.created_at.asc()).limit(500).all()
    return [{"id": item.id, "body": item.body, "created_at": item.created_at.isoformat(), "user": {"id": item.user.id, "username": item.user.username}} for item in comments]


@router.post("/videos/{video_id}/comments", status_code=201)
def add_comment(video_id: int, payload: CommentCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = get_visible_video(db, video_id, user)
    comment = Comment(video_id=video.id, user_id=user.id, body=payload.body.strip())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {"id": comment.id, "body": comment.body, "created_at": comment.created_at.isoformat(), "user": {"id": user.id, "username": user.username}}


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    comment = db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Комментарий не найден")
    if comment.user_id != user.id and user.role not in {"moderator", "admin"}:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    db.delete(comment)
    db.commit()
    return {"message": "Комментарий удалён"}


@router.post("/videos/{video_id}/report", status_code=201)
def report_video(video_id: int, payload: ReportCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = get_visible_video(db, video_id, user)
    if video.owner_id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя пожаловаться на собственное видео")
    existing = db.query(Report).filter_by(video_id=video.id, reporter_id=user.id, status="open").first()
    if existing:
        raise HTTPException(status_code=409, detail="У вас уже есть открытая жалоба на это видео")
    report = Report(video_id=video.id, reporter_id=user.id, reason=payload.reason, details=payload.details)
    db.add(report)
    db.commit()
    return {"message": "Жалоба отправлена", "report_id": report.id}


@router.get("/videos/{video_id}/access")
def list_access(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    if video.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Только владелец может управлять доступом")
    grants = db.query(VideoAccess).options(joinedload(VideoAccess.user)).filter_by(video_id=video.id).all()
    return [{"user_id": item.user.id, "username": item.user.username, "email": item.user.email} for item in grants]


@router.post("/videos/{video_id}/access", status_code=201)
def grant_access(video_id: int, payload: AccessGrantCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    if video.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Только владелец может выдавать доступ")
    target = db.query(User).filter(User.email == payload.email.lower()).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь с таким email не найден")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Владелец уже имеет доступ")
    grant = db.query(VideoAccess).filter_by(video_id=video.id, user_id=target.id).first()
    if not grant:
        db.add(VideoAccess(video_id=video.id, user_id=target.id))
        db.commit()
    return {"message": f"Доступ выдан пользователю {target.username}"}


@router.delete("/videos/{video_id}/access/{target_user_id}")
def revoke_access(video_id: int, target_user_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    if video.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Только владелец может отзывать доступ")
    grant = db.query(VideoAccess).filter_by(video_id=video.id, user_id=target_user_id).first()
    if grant:
        db.delete(grant)
        db.commit()
    return {"message": "Доступ отозван"}

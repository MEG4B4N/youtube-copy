from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload
from app.core.dependencies import require_moderator
from app.db import get_db
from app.models import Report, User, Video

router = APIRouter(prefix="/api/moderation", tags=["Модерация"])


class ResolveReport(BaseModel):
    status: str = Field(pattern="^(resolved|dismissed)$")
    hide_video: bool = False


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), moderator: User = Depends(require_moderator)):
    reports = db.query(Report).options(joinedload(Report.video), joinedload(Report.reporter)).order_by(Report.created_at.desc()).limit(500).all()
    return [{"id": item.id, "video_id": item.video_id, "video_title": item.video.title, "reporter": item.reporter.username,
             "reason": item.reason, "details": item.details, "status": item.status,
             "created_at": item.created_at.isoformat()} for item in reports]


@router.patch("/reports/{report_id}")
def resolve_report(report_id: int, payload: ResolveReport, db: Session = Depends(get_db), moderator: User = Depends(require_moderator)):
    report = db.query(Report).options(joinedload(Report.video)).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Жалоба не найдена")
    report.status = payload.status
    report.moderator_id = moderator.id
    report.resolved_at = datetime.now(timezone.utc)
    if payload.hide_video:
        report.video.is_hidden = True
    db.commit()
    return {"message": "Жалоба обработана", "status": report.status, "video_hidden": report.video.is_hidden}


@router.post("/videos/{video_id}/hide")
def hide_video(video_id: int, db: Session = Depends(get_db), moderator: User = Depends(require_moderator)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    video.is_hidden = True
    db.commit()
    return {"message": "Видео скрыто"}


@router.post("/videos/{video_id}/restore")
def restore_video(video_id: int, db: Session = Depends(get_db), moderator: User = Depends(require_moderator)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    video.is_hidden = False
    db.commit()
    return {"message": "Видео восстановлено"}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload
from app.api.common import serialize_videos
from app.core.dependencies import get_current_user, require_user
from app.db import get_db
from app.models import Playlist, PlaylistVideo, Subscription, User, Video
from app.schemas import PlaylistAddVideo, PlaylistCreate

router = APIRouter(prefix="/api", tags=["Каналы и плейлисты"])


@router.get("/channels/{username}")
def get_channel(username: str, db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user)):
    channel = db.query(User).filter(User.username == username).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Канал не найден")
    subscriber_count = db.query(func.count(Subscription.id)).filter_by(channel_id=channel.id).scalar() or 0
    video_count_query = db.query(func.count(Video.id)).filter_by(owner_id=channel.id, status="ready", is_hidden=False)
    if not viewer or viewer.id != channel.id:
        video_count_query = video_count_query.filter(Video.visibility == "public")
    video_count = video_count_query.scalar() or 0
    subscribed = bool(viewer and db.query(Subscription).filter_by(subscriber_id=viewer.id, channel_id=channel.id).first())
    video_query = db.query(Video).options(joinedload(Video.owner)).filter(
        Video.owner_id == channel.id, Video.status == "ready", Video.is_hidden.is_(False)
    )
    if not viewer or viewer.id != channel.id:
        video_query = video_query.filter(Video.visibility == "public")
    videos = video_query.order_by(Video.created_at.desc()).limit(60).all()
    playlist_query = db.query(Playlist).filter(Playlist.owner_id == channel.id)
    if not viewer or viewer.id != channel.id:
        playlist_query = playlist_query.filter(Playlist.visibility == "public")
    playlists = playlist_query.order_by(Playlist.created_at.desc()).all()
    return {
        "channel": {"id": channel.id, "username": channel.username, "bio": channel.bio, "role": channel.role,
                    "subscriber_count": subscriber_count, "video_count": video_count, "is_subscribed": subscribed,
                    "is_owner": bool(viewer and viewer.id == channel.id)},
        "videos": serialize_videos(db, videos, viewer),
        "playlists": [{"id": item.id, "title": item.title, "description": item.description, "visibility": item.visibility,
                       "video_count": len(item.items)} for item in playlists],
    }


@router.get("/me/playlists")
def list_my_playlists(db: Session = Depends(get_db), user: User = Depends(require_user)):
    playlists = db.query(Playlist).filter(Playlist.owner_id == user.id).order_by(desc(Playlist.created_at)).limit(100).all()
    return {"items": [
        {"id": item.id, "title": item.title, "description": item.description,
         "visibility": item.visibility, "video_count": len(item.items)}
        for item in playlists
    ]}


@router.get("/subscriptions/feed")
def subscription_feed(db: Session = Depends(get_db), user: User = Depends(require_user)):
    videos = db.query(Video).join(
        Subscription, Subscription.channel_id == Video.owner_id
    ).options(joinedload(Video.owner)).filter(
        Subscription.subscriber_id == user.id,
        Video.visibility == "public",
        Video.status == "ready",
        Video.is_hidden.is_(False),
    ).order_by(desc(Video.created_at)).limit(60).all()
    return {"items": serialize_videos(db, videos, user)}


@router.post("/channels/{username}/subscribe")
def toggle_subscription(username: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    channel = db.query(User).filter(User.username == username).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Канал не найден")
    if channel.id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя подписаться на собственный канал")
    existing = db.query(Subscription).filter_by(subscriber_id=user.id, channel_id=channel.id).first()
    if existing:
        db.delete(existing)
        subscribed = False
    else:
        db.add(Subscription(subscriber_id=user.id, channel_id=channel.id))
        subscribed = True
    db.commit()
    count = db.query(func.count(Subscription.id)).filter_by(channel_id=channel.id).scalar() or 0
    return {"subscribed": subscribed, "subscriber_count": count}


@router.post("/playlists", status_code=201)
def create_playlist(payload: PlaylistCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    playlist = Playlist(owner_id=user.id, title=payload.title.strip(), description=payload.description, visibility=payload.visibility)
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return {"id": playlist.id, "title": playlist.title, "visibility": playlist.visibility}


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(get_current_user)):
    playlist = db.query(Playlist).options(joinedload(Playlist.items).joinedload(PlaylistVideo.video).joinedload(Video.owner)).filter(Playlist.id == playlist_id).first()
    if not playlist or (playlist.visibility == "private" and (not viewer or viewer.id != playlist.owner_id)):
        raise HTTPException(status_code=404, detail="Плейлист не найден")
    videos = [item.video for item in playlist.items if item.video and not item.video.is_hidden and item.video.status == "ready"]
    if not viewer or viewer.id != playlist.owner_id:
        videos = [item for item in videos if item.visibility == "public"]
    return {"id": playlist.id, "title": playlist.title, "description": playlist.description,
            "owner": playlist.owner.username, "videos": serialize_videos(db, videos, viewer)}


@router.post("/playlists/{playlist_id}/videos", status_code=201)
def add_to_playlist(playlist_id: int, payload: PlaylistAddVideo, db: Session = Depends(get_db), user: User = Depends(require_user)):
    playlist = db.get(Playlist, playlist_id)
    video = db.get(Video, payload.video_id)
    if not playlist or playlist.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Плейлист не найден")
    if not video or (video.visibility == "private" and video.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Видео не найдено")
    if db.query(PlaylistVideo).filter_by(playlist_id=playlist.id, video_id=video.id).first():
        return {"message": "Видео уже находится в плейлисте"}
    position = db.query(func.count(PlaylistVideo.id)).filter_by(playlist_id=playlist.id).scalar() or 0
    db.add(PlaylistVideo(playlist_id=playlist.id, video_id=video.id, position=position))
    db.commit()
    return {"message": "Видео добавлено в плейлист"}

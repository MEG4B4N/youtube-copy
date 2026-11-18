from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Comment, Like, Subscription, User, Video, VideoAccess


def serialize_video(db: Session, video: Video, viewer: User | None = None, batch_data: dict | None = None) -> dict:
    owner = video.owner
    if batch_data is None:
        like_count = len(video.likes)
        comment_count = len(video.comments)
        liked = bool(viewer and any(item.user_id == viewer.id for item in video.likes))
        subscribed = bool(viewer and db.query(Subscription).filter_by(
            subscriber_id=viewer.id, channel_id=owner.id
        ).first())
    else:
        like_count = batch_data["like_counts"].get(video.id, 0)
        comment_count = batch_data["comment_counts"].get(video.id, 0)
        liked = bool(viewer and video.id in batch_data["liked_ids"])
        subscribed = bool(viewer and owner.id in batch_data["subscribed_channels"])

    return {
        "id": video.id,
        "title": video.title,
        "description": video.description,
        "visibility": video.visibility,
        "status": video.status,
        "duration": video.duration,
        "views": video.views,
        "like_count": like_count,
        "comment_count": comment_count,
        "is_liked": liked,
        "is_subscribed": subscribed,
        "is_hidden": video.is_hidden,
        "created_at": video.created_at.isoformat(),
        "owner": {"id": owner.id, "username": owner.username, "role": owner.role},
        "thumbnail_url": f"/api/videos/{video.id}/thumbnail" if video.thumbnail_key else None,
        "stream_url": f"/api/videos/{video.id}/stream" if video.status == "ready" else None,
    }


def serialize_videos(db: Session, videos: list[Video], viewer: User | None = None) -> list[dict]:
    """Serialize a feed in a fixed number of aggregate queries instead of N+1 queries."""
    if not videos:
        return []

    video_ids = [video.id for video in videos]
    owner_ids = {video.owner_id for video in videos}
    like_counts = dict(db.query(Like.video_id, func.count(Like.id)).filter(
        Like.video_id.in_(video_ids)
    ).group_by(Like.video_id).all())
    comment_counts = dict(db.query(Comment.video_id, func.count(Comment.id)).filter(
        Comment.video_id.in_(video_ids)
    ).group_by(Comment.video_id).all())

    liked_ids: set[int] = set()
    subscribed_channels: set[int] = set()
    if viewer:
        liked_ids = {video_id for (video_id,) in db.query(Like.video_id).filter(
            Like.user_id == viewer.id, Like.video_id.in_(video_ids)
        ).all()}
        subscribed_channels = {channel_id for (channel_id,) in db.query(Subscription.channel_id).filter(
            Subscription.subscriber_id == viewer.id,
            Subscription.channel_id.in_(owner_ids),
        ).all()}

    stats = {
        "like_counts": like_counts,
        "comment_counts": comment_counts,
        "liked_ids": liked_ids,
        "subscribed_channels": subscribed_channels,
    }
    return [serialize_video(db, video, viewer, stats) for video in videos]


def get_visible_video(db: Session, video_id: int, viewer: User | None) -> Video:
    video = db.get(Video, video_id)
    if not video or video.is_hidden or video.status not in {"ready", "processing", "failed"}:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    if video.visibility == "private":
        allowed = bool(viewer and (viewer.id == video.owner_id or db.query(VideoAccess).filter_by(video_id=video.id, user_id=viewer.id).first()))
        if not allowed:
            raise HTTPException(status_code=404, detail="Видео не найдено")
    return video


def ensure_owner_or_moderator(video: Video, user: User) -> None:
    if video.owner_id != user.id and user.role not in {"moderator", "admin"}:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

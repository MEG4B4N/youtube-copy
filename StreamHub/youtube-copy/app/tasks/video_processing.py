import os
import subprocess
import tempfile
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import SessionLocal
from app.models import Video
from app.services.storage import get_object, upload_file
from app.tasks.celery_app import celery_app


@celery_app.task(name="process_video", bind=True, max_retries=2)
def process_video(self, video_id: int):
    db: Session = SessionLocal()
    try:
        video = db.get(Video, video_id)
        if not video:
            return {"status": "missing"}
        video.status = "processing"
        db.commit()

        with tempfile.TemporaryDirectory(prefix="streamhub-") as workdir:
            source_path = os.path.join(workdir, "source")
            output_path = os.path.join(workdir, "processed.mp4")
            thumb_path = os.path.join(workdir, "thumbnail.jpg")
            obj = get_object(video.original_key)
            with open(source_path, "wb") as target:
                body = obj["Body"]
                for chunk in iter(lambda: body.read(1024 * 1024), b""):
                    target.write(chunk)
                body.close()

            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", source_path],
                capture_output=True, text=True, check=True, timeout=60,
            )
            duration = max(0.0, float(probe.stdout.strip() or 0))
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source_path,
                 "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                 "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output_path],
                capture_output=True, check=True, timeout=60 * 60,
            )
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1", "-i", output_path,
                 "-frames:v", "1", "-q:v", "3", thumb_path],
                capture_output=True, check=True, timeout=120,
            )
            processed_key = f"videos/{video.id}/processed.mp4"
            thumbnail_key = f"videos/{video.id}/thumbnail.jpg"
            upload_file(output_path, processed_key, "video/mp4")
            upload_file(thumb_path, thumbnail_key, "image/jpeg")

        video = db.get(Video, video_id)
        video.processed_key = processed_key
        video.thumbnail_key = thumbnail_key
        video.duration = duration
        video.status = "ready"
        video.processing_error = None
        db.commit()
        return {"status": "ready", "video_id": video_id}
    except Exception as exc:
        db.rollback()
        video = db.get(Video, video_id)
        if video:
            video.status = "failed"
            video.processing_error = str(exc)[:1000]
            db.commit()
        raise
    finally:
        db.close()

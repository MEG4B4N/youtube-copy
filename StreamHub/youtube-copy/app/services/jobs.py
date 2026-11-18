def enqueue_video_processing(video_id: int) -> None:
    # Import Celery only when an upload is actually queued; API tests and docs
    # can load the application without booting a worker process.
    from app.tasks.video_processing import process_video
    process_video.delay(video_id)

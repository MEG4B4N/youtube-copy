# AI agent instructions — StreamHub

## Product intent
Build a small but coherent YouTube-like video platform. Correct access control and the media lifecycle are more important than adding decorative features.

## Fixed stack
- Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic.
- PostgreSQL for relational data; S3-compatible object storage (RustFS in Docker Compose) for original and derived media.
- Redis + Celery for asynchronous media processing; FFmpeg/ffprobe in the worker image.
- Plain HTML/CSS/JavaScript served by FastAPI.

## Engineering rules
1. Keep media bytes out of PostgreSQL. Store object keys only.
2. Every private-video read path must call the same access policy: owner or explicit `video_access` grant. Do not expose private media through feed/search/channel/playlist/thumbnail/stream endpoints.
3. Keep roles server-enforced: user, moderator, admin. Hiding content and handling reports require moderator/admin.
4. Validate upload extension and size; never trust client-provided MIME type as proof of content.
5. Keep long-running FFmpeg work out of request handlers. Persist state transitions and use the worker.
6. Preserve byte-range support for media streaming.
7. Add or update tests for authorization, access control, and state transitions whenever changing those behaviors.
8. Use Alembic migrations for schema changes. Never rely on production `create_all`.
9. Do not commit secrets, `.env`, private AI exports, or user data.
10. Update `README.md` and `docs/` when commands, API behavior, or infrastructure change.

## Definition of done
- Static compilation succeeds and tests pass.
- A clean Compose deployment runs migrations, seeds demo accounts, and starts API and worker.
- Public/private media behavior is covered by tests.
- Error responses do not disclose object-store credentials, passwords, or stack traces.

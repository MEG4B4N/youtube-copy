from app.core.security import hash_password
from app.models import User, Video


def register(client, username="viewer", email="viewer@example.com"):
    response = client.post("/api/auth/register", json={"username": username, "email": email, "password": "StrongPass123!"})
    assert response.status_code == 201, response.text
    return response.json()["user"]


def make_video(db, owner, *, visibility="public", status="ready"):
    video = Video(owner_id=owner.id, title="Тестовый ролик", description="Описание", visibility=visibility,
                  status=status, original_key="originals/test.mp4", processed_key="processed/test.mp4" if status == "ready" else None,
                  thumbnail_key="thumbs/test.jpg" if status == "ready" else None, duration=15.0)
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def test_register_login_and_current_user(client):
    user = register(client)
    assert user["username"] == "viewer"
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    login = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "StrongPass123!"})
    assert login.status_code == 200
    assert client.get("/api/auth/me").json()["id"] == user["id"]


def test_duplicate_username_or_email_is_rejected(client):
    register(client)
    response = client.post("/api/auth/register", json={"username": "viewer", "email": "other@example.com", "password": "StrongPass123!"})
    assert response.status_code == 409


def test_private_video_is_hidden_until_owner_grants_access(client, db_session):
    owner_client = client
    owner = register(owner_client, "owner", "owner@example.com")
    db_owner = db_session.get(User, owner["id"])
    video = make_video(db_session, db_owner, visibility="private")

    guest_client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(owner_client.app)
    guest = register(guest_client, "guest", "guest@example.com")
    assert guest["id"] != owner["id"]
    assert guest_client.get(f"/api/videos/{video.id}").status_code == 404

    grant = owner_client.post(f"/api/videos/{video.id}/access", json={"email": "guest@example.com"})
    assert grant.status_code == 201
    assert guest_client.get(f"/api/videos/{video.id}").status_code == 200

    revoke = owner_client.delete(f"/api/videos/{video.id}/access/{guest['id']}")
    assert revoke.status_code == 200
    assert guest_client.get(f"/api/videos/{video.id}").status_code == 404
    guest_client.close()


def test_like_and_comment_require_authentication_and_work(client, db_session):
    user_data = register(client)
    owner = db_session.get(User, user_data["id"])
    video = make_video(db_session, owner)
    like = client.post(f"/api/videos/{video.id}/like")
    assert like.status_code == 200
    assert like.json()["liked"] is True
    assert like.json()["like_count"] == 1
    comment = client.post(f"/api/videos/{video.id}/comments", json={"body": "Хорошее видео"})
    assert comment.status_code == 201
    assert comment.json()["body"] == "Хорошее видео"
    assert len(client.get(f"/api/videos/{video.id}/comments").json()) == 1


def test_upload_saves_metadata_and_queues_worker(client, db_session, monkeypatch):
    user_data = register(client)
    from app.api import videos as video_routes
    monkeypatch.setattr(video_routes, "upload_file", lambda path, key, content_type: None)
    queued = []
    monkeypatch.setattr(video_routes, "enqueue_video_processing", lambda video_id: queued.append(video_id))
    response = client.post("/api/videos/upload", data={"title": "Uploaded test", "description": "Upload description", "visibility": "private"},
                           files={"file": ("demo.mp4", b"\x00\x00\x00\x18ftypisomfake-video-bytes", "video/mp4")})
    assert response.status_code == 201, response.text
    payload = response.json()["video"]
    assert payload["title"] == "Uploaded test"
    assert payload["visibility"] == "private"
    assert queued == [payload["id"]]


def test_moderation_requires_moderator_role(client, db_session):
    register(client)
    assert client.get("/api/moderation/reports").status_code == 403
    moderator = User(username="mod", email="mod@example.com", hashed_password=hash_password("ModPass123!"), role="moderator")
    db_session.add(moderator)
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": "mod@example.com", "password": "ModPass123!"})
    assert login.status_code == 200
    assert client.get("/api/moderation/reports").status_code == 200


def test_channel_search_subscribe_playlist_and_moderation(client, db_session):
    owner_data = register(client, "creator", "creator@example.com")
    owner = db_session.get(User, owner_data["id"])
    video = make_video(db_session, owner)

    playlist_response = client.post("/api/playlists", json={"title": "Favorites", "description": "List", "visibility": "public"})
    assert playlist_response.status_code == 201
    playlist_id = playlist_response.json()["id"]
    assert client.post(f"/api/playlists/{playlist_id}/videos", json={"video_id": video.id}).status_code == 201

    channel = client.get("/api/channels/creator")
    assert channel.status_code == 200
    assert channel.json()["channel"]["video_count"] == 1
    assert channel.json()["videos"][0]["id"] == video.id
    assert len(channel.json()["playlists"]) == 1
    assert client.get(f"/api/playlists/{playlist_id}").json()["videos"][0]["id"] == video.id

    guest_client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(client.app)
    register(guest_client, "guest2", "guest2@example.com")
    assert len(guest_client.get("/api/search?q=Тестовый").json()["items"]) == 1
    subscription = guest_client.post("/api/channels/creator/subscribe")
    assert subscription.status_code == 200 and subscription.json()["subscribed"] is True
    report = guest_client.post(f"/api/videos/{video.id}/report", json={"reason": "other", "details": "Проверка модерации"})
    assert report.status_code == 201

    moderator = User(username="moderator", email="moderator@example.com", hashed_password=hash_password("ModPass123!"), role="moderator")
    db_session.add(moderator)
    db_session.commit()
    moderator_client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(client.app)
    assert moderator_client.post("/api/auth/login", json={"email": "moderator@example.com", "password": "ModPass123!"}).status_code == 200
    reports = moderator_client.get("/api/moderation/reports")
    assert reports.status_code == 200 and len(reports.json()) == 1
    resolved = moderator_client.patch(f"/api/moderation/reports/{report.json()['report_id']}", json={"status": "resolved", "hide_video": True})
    assert resolved.status_code == 200 and resolved.json()["video_hidden"] is True
    assert guest_client.get(f"/api/videos/{video.id}").status_code == 404
    guest_client.close()
    moderator_client.close()


def test_stream_endpoint_supports_byte_ranges(client, db_session, monkeypatch):
    import io
    user_data = register(client)
    owner = db_session.get(User, user_data["id"])
    video = make_video(db_session, owner)
    from app.api import videos as video_routes
    monkeypatch.setattr(video_routes, "head_object", lambda key: {"ContentLength": 10})
    monkeypatch.setattr(video_routes, "get_object", lambda key, byte_range=None: {"Body": io.BytesIO(b"01234"), "ContentLength": 5})
    response = client.get(f"/api/videos/{video.id}/stream", headers={"Range": "bytes=0-4"})
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-4/10"
    assert response.content == b"01234"


def test_personal_library_endpoints_and_subscription_feed(client, db_session):
    from fastapi.testclient import TestClient

    owner_data = register(client, "creator", "creator@example.com")
    owner = db_session.get(User, owner_data["id"])
    video = make_video(db_session, owner)

    assert client.post(f"/api/videos/{video.id}/like").status_code == 200
    liked = client.get("/api/me/liked")
    assert liked.status_code == 200
    assert [item["id"] for item in liked.json()["items"]] == [video.id]

    own_videos = client.get("/api/me/videos")
    assert own_videos.status_code == 200
    assert [item["id"] for item in own_videos.json()["items"]] == [video.id]

    playlist = client.post("/api/playlists", json={"title": "Saved", "description": "Library", "visibility": "private"})
    assert playlist.status_code == 201
    assert client.post(f"/api/playlists/{playlist.json()['id']}/videos", json={"video_id": video.id}).status_code == 201
    my_playlists = client.get("/api/me/playlists")
    assert my_playlists.status_code == 200
    assert my_playlists.json()["items"][0]["video_count"] == 1

    subscriber_client = TestClient(client.app)
    register(subscriber_client, "subscriber", "subscriber@example.com")
    subscribed = subscriber_client.post("/api/channels/creator/subscribe")
    assert subscribed.status_code == 200 and subscribed.json()["subscribed"] is True
    feed = subscriber_client.get("/api/subscriptions/feed")
    assert feed.status_code == 200
    assert [item["id"] for item in feed.json()["items"]] == [video.id]
    subscriber_client.close()


def test_personal_library_endpoints_require_authentication(client):
    for path in ("/api/me/liked", "/api/me/videos", "/api/me/playlists", "/api/subscriptions/feed"):
        assert client.get(path).status_code == 401


def test_download_endpoint_returns_attachment_and_streams_content(client, db_session, monkeypatch):
    import io
    from app.api import videos as video_routes

    user_data = register(client, "downloader", "downloader@example.com")
    owner = db_session.get(User, user_data["id"])
    video = make_video(db_session, owner)
    monkeypatch.setattr(video_routes, "head_object", lambda key: {"ContentLength": 5})
    monkeypatch.setattr(video_routes, "get_object", lambda key, byte_range=None: {"Body": io.BytesIO(b"video"), "ContentLength": 5})

    response = client.get(f"/api/videos/{video.id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content == b"video"


def test_demo_seed_adds_missing_titles_without_duplicates(monkeypatch):
    from pathlib import Path
    from app import seed as seed_module
    from app.db import SessionLocal
    from app.models import Playlist

    uploads = []
    monkeypatch.setattr(seed_module, "ensure_bucket", lambda: None)
    monkeypatch.setattr(seed_module, "upload_file", lambda path, key, content_type: uploads.append(key))
    monkeypatch.setattr(seed_module, "create_cover", lambda path, title, tag, accent, theme: Path(path).write_bytes(b"cover"))
    monkeypatch.setattr(seed_module, "create_motion_clip", lambda cover, output, duration=12: Path(output).write_bytes(b"mp4"))
    monkeypatch.setattr(seed_module, "_extract_thumbnail", lambda video, thumb: Path(thumb).write_bytes(b"thumb"))
    monkeypatch.setattr(seed_module, "SessionLocal", SessionLocal)

    seed_module.seed()
    first_upload_count = len(uploads)
    db = SessionLocal()
    try:
        assert db.query(Video).count() == 9
        assert db.query(Playlist).count() == 1
    finally:
        db.close()

    seed_module.seed()
    db = SessionLocal()
    try:
        assert db.query(Video).count() == 9
        assert len(uploads) == first_upload_count
    finally:
        db.close()

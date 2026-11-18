import os
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/streamhub-tests.sqlite3")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-that-is-long-enough-for-tests")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test-secret")
os.environ.setdefault("COOKIE_SECURE", "false")

import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine, SessionLocal
from app import models  # noqa: F401
from app.main import app
import app.main as main_module


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main_module, "ensure_bucket", lambda: None)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

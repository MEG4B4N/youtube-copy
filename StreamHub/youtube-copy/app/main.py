from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.api import auth, channels, moderation, videos
from app.core.config import settings
from app.services.storage import ensure_bucket

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_bucket()
    yield


app = FastAPI(
    title=f"{settings.app_name} API",
    description="Видеоплатформа с каналами, приватным доступом, комментариями и модерацией.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(channels.router)
app.include_router(moderation.router)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.middleware("http")
async def same_origin_guard(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        host = request.headers.get("host")
        if origin and host:
            from urllib.parse import urlparse
            if urlparse(origin).netloc.lower() != host.lower():
                return JSONResponse(status_code=403, content={"detail": "Cross-origin запрос отклонён"})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_routes(full_path: str):
    if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "health", "assets/")):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return FileResponse(FRONTEND_DIR / "index.html")

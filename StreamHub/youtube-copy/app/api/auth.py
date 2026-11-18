from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.dependencies import get_current_user, require_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["Авторизация"])


def public_user(user: User) -> dict:
    return {"id": user.id, "username": user.username, "email": user.email, "role": user.role, "bio": user.bio}


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="streamhub_access", value=token, httponly=True, secure=settings.cookie_secure,
        samesite="lax", max_age=settings.access_token_expire_minutes * 60, path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower()
    username = payload.username.strip().lower()
    if db.query(User).filter(or_(User.email == email, User.username == username)).first():
        raise HTTPException(status_code=409, detail="Пользователь с таким email или именем уже существует")
    user = User(username=username, email=email, hashed_password=hash_password(payload.password), role="user")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id))
    set_auth_cookie(response, token)
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт отключён")
    token = create_access_token(str(user.id))
    set_auth_cookie(response, token)
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("streamhub_access", path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")
    return {"message": "Вы вышли из аккаунта"}


@router.get("/me")
def me(user: User = Depends(require_user)):
    return public_user(user)

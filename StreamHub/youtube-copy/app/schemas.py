from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
    bio: str
    created_at: datetime


class VideoMetadata(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=10000)
    visibility: str = Field(default="public", pattern="^(public|private)$")


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ReportCreate(BaseModel):
    reason: str = Field(pattern="^(spam|misleading|copyright|violence|hate|sexual|other)$")
    details: str = Field(default="", max_length=2000)


class AccessGrantCreate(BaseModel):
    email: EmailStr


class PlaylistCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    visibility: str = Field(default="public", pattern="^(public|private)$")


class PlaylistAddVideo(BaseModel):
    video_id: int

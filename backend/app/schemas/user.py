"""User Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.models.user import UserRole


class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: UserRole = UserRole.viewer


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    password: Optional[str] = None


class UserResponse(UserBase):
    email: str  # Relax validation for output (e.g., handles "admin@jaldrishti.local")
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

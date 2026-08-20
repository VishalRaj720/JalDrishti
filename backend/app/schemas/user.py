"""User Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.models.user import UserRole


def _reject_unassignable_role(v: Optional[UserRole]) -> Optional[UserRole]:
    """`viewer` is a dead enum value and must not be assignable.

    R12. `regulator` used to be rejected here, because R7 had merged it into
    `admin` and an account really was created on the dead role — every
    `require_admin` guard then refused that user with nothing on screen saying
    why. It is a REAL role again, with a narrower job than it had before
    (reviewing field submissions, and nothing else), so the block is gone.

    `viewer` stays blocked. Migration 0008 migrated those accounts to `citizen`
    and nothing has recognised the value since; Postgres simply cannot drop an
    enum label transactionally, which is the only reason it still exists.

    Rejected at the schema so the API, the seed and any script hit one wall.
    """
    if v is not None and v.value == "viewer":
        raise ValueError(
            "The 'viewer' role was replaced by 'citizen' in migration 0008 and "
            "is not assignable. Use 'citizen'.")
    return v


class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: UserRole = UserRole.citizen


    _no_dead_role = field_validator("role")(_reject_unassignable_role)


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    password: Optional[str] = None

    _no_dead_role = field_validator("role")(_reject_unassignable_role)


class UserResponse(UserBase):
    email: str  # Relax validation for output (e.g., handles "admin@jaldrishti.local")
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

"""User Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.models.user import UserRole


def _reject_retired_role(v: Optional[UserRole]) -> Optional[UserRole]:
    """`regulator` was retired in R7 and must not be assignable.

    The enum value still exists because Postgres cannot drop one
    transactionally, so it stayed *assignable* long after it stopped being
    recognised — and an account really was created with it. Every
    `require_admin` guard then rejected that user, so they could not publish,
    reach the dataset manager, or read the audit log, with nothing on screen
    explaining why. Their role pill read "Administrator (former regulator)",
    which was the only clue.

    Rejected at the schema so the API, the seed and any script hit the same wall.
    """
    if v is not None and v.value == "regulator":
        raise ValueError(
            "The 'regulator' role was retired: admin holds every power it had. "
            "Assign 'admin' instead. An account left on this role is refused by "
            "every admin guard in the system.")
    return v


class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: UserRole = UserRole.citizen


    _no_retired_role = field_validator("role")(_reject_retired_role)


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    password: Optional[str] = None

    _no_retired_role = field_validator("role")(_reject_retired_role)


class UserResponse(UserBase):
    email: str  # Relax validation for output (e.g., handles "admin@jaldrishti.local")
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

"""User service."""
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user import UserRepository
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth import hash_password, verify_password
from app.exceptions import (AppValidationError, DuplicateResourceError,
                            ResourceNotFoundError, AuthenticationError)


class UserService:
    """User management, with one structural rule: there is exactly one admin.

    R12. `admin` is the product owner's own account — it operates the dataset
    pipeline, the factory reset and the model. A second admin is not a
    convenience, it is a second person who can rewrite the evidence base, and
    the audit trail cannot tell you which of them a decision came from in any
    way that matters operationally.

    Reviewing what a field officer submits is now `regulator`, of which there
    may be as many as needed. That is the role a second operator should get.

    Enforced HERE rather than in the router so the API, a script and the seed
    all hit the same wall — and backed by a partial unique index in migration
    0022, because an application check is a race between two requests and an
    index is not.
    """

    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)
        self.db = db

    async def _refuse_second_admin(self, *, excluding: Optional[uuid.UUID] = None
                                   ) -> None:
        """Raise unless this account would be the only admin."""
        from sqlalchemy import func, select

        stmt = select(func.count()).select_from(User).where(
            User.role == UserRole.admin)
        if excluding is not None:
            stmt = stmt.where(User.id != excluding)
        existing = (await self.db.execute(stmt)).scalar() or 0
        if existing:
            raise AppValidationError(
                "This deployment already has an administrator, and there is "
                "exactly one by design: the admin account operates the dataset "
                "pipeline, the factory reset and the model. To give someone the "
                "power to review and approve field submissions, assign "
                "'regulator' — that is what the role is for, and there may be "
                "as many regulators as you need.")

    async def create_user(self, data: UserCreate) -> User:
        if await self.repo.get_by_email(data.email):
            raise DuplicateResourceError("User", "email", data.email)
        if await self.repo.get_by_username(data.username):
            raise DuplicateResourceError("User", "username", data.username)
        if UserRole(data.role) is UserRole.admin:
            await self._refuse_second_admin()
        return await self.repo.create({
            "username": data.username,
            "email": data.email,
            "hashed_password": hash_password(data.password),
            "role": UserRole(data.role),
        })

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password.")
        return user

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.repo.get(user_id)
        if not user:
            raise ResourceNotFoundError("User", str(user_id))
        return user

    async def list_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        return await self.repo.get_all(skip=skip, limit=limit)

    async def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get_user(user_id)
        updates = data.model_dump(exclude_none=True)
        # Promotion is the other door into a second admin, and it is the one a
        # UI makes easy: pick a user, change the dropdown, save.
        if "role" in updates and UserRole(updates["role"]) is UserRole.admin:
            await self._refuse_second_admin(excluding=user_id)
        if "password" in updates:
            updates["hashed_password"] = hash_password(updates.pop("password"))
        return await self.repo.update(user, updates)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        user = await self.get_user(user_id)
        await self.repo.delete(user)

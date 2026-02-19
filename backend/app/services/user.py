"""User service."""
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user import UserRepository
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth import hash_password, verify_password
from app.exceptions import DuplicateResourceError, ResourceNotFoundError, AuthenticationError


class UserService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def create_user(self, data: UserCreate) -> User:
        if await self.repo.get_by_email(data.email):
            raise DuplicateResourceError("User", "email", data.email)
        if await self.repo.get_by_username(data.username):
            raise DuplicateResourceError("User", "username", data.username)
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
        if "password" in updates:
            updates["hashed_password"] = hash_password(updates.pop("password"))
        return await self.repo.update(user, updates)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        user = await self.get_user(user_id)
        await self.repo.delete(user)

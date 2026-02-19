"""Users router (admin-only CRUD)."""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.user import UserService
from app.dependencies import require_admin, require_any_role
from app.exceptions import AppException

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    return await UserService(db).list_users(skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        return await UserService(db).get_user(user_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        return await UserService(db).create_user(payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        return await UserService(db).update_user(user_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        await UserService(db).delete_user(user_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

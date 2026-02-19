"""Common/shared Pydantic schemas."""
import uuid
from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int


class MessageResponse(BaseModel):
    message: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str

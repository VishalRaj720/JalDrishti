"""Auth Pydantic schemas."""
from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "viewer"


class LoginRequest(BaseModel):
    email: str   # plain str to accept .local and other non-standard TLDs
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPayload(BaseModel):
    sub: str          # user id
    role: str
    exp: int
    type: str = "access"

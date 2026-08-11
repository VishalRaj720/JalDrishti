"""Auth Pydantic schemas.

`SignupRequest` was deleted in P2 along with the endpoint that consumed it. Its
`role: str = "viewer"` field was client-settable on an unauthenticated route and
flowed unchecked into `UserRole(...)`, which let anyone mint themselves an
admin. See `app/api/v1/auth.py` for the full account.
"""
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str   # plain str to accept .local and other non-standard TLDs
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str          # user id
    role: str
    exp: int
    type: str = "access"

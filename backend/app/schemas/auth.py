"""Authentication request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Role


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthenticatedUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    institution_id: str | None
    full_name: str
    email: str
    role: Role
    active: bool
    created_at: datetime

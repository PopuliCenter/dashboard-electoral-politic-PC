"""Skema login dan pengguna (T5.1)."""

import uuid

from pydantic import BaseModel, Field

from app.core.security import MAX_PASSWORD_LENGTH
from app.models.enums import RoleCode


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: RoleCode

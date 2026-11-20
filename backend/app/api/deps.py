"""Dependensi autentikasi dan otorisasi (T5.1)."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.models import User, UserSession
from app.models.enums import RoleCode
from app.services import auth


def client_ip(request: Request) -> str | None:
    # Di belakang Nginx (T6.1), alamat asli diteruskan lewat proxy_headers uvicorn.
    return request.client.host if request.client else None


async def current_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserSession:
    token = request.cookies.get(settings.session_cookie_name)
    found = await auth.resolve_session(session, settings, token)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="belum login atau sesi sudah berakhir",
        )
    # Perpanjangan batas idle ditulis di resolve_session.
    await session.commit()
    return found


async def current_user(user_session: UserSession = Depends(current_session)) -> User:
    return user_session.user


def require_role(*roles: RoleCode) -> Callable[..., Awaitable[User]]:
    async def dependency(user: User = Depends(current_user)) -> User:
        if user.role.role_code not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="peran Anda tidak diizinkan"
            )
        return user

    return dependency


require_admin = require_role(RoleCode.ADMIN)

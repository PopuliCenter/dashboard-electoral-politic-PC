"""Login, logout, dan pengguna saat ini (T5.1).

Sesi disimpan di cookie HttpOnly (tidak terbaca JavaScript), SameSite=Lax, dan
Secure di luar pengembangan. Tokennya hanya ada di cookie; database menyimpan
hash-nya.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, current_session, current_user
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.models import User, UserSession
from app.schemas.auth import LoginIn, UserOut
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role.role_code)


@router.post("/login", response_model=UserOut, summary="Login dengan email dan password")
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    try:
        result = await auth.login(
            session,
            settings,
            body.email,
            body.password,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except auth.LoginError as exc:
        # Simpan penghitung gagal dan jejak audit sebelum menolak.
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    await session.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=result.token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user_out(result.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Akhiri sesi ini")
async def logout(
    request: Request,
    response: Response,
    user_session: UserSession = Depends(current_session),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    await auth.logout(session, user_session, client_ip(request))
    await session.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut, summary="Pengguna yang sedang login")
async def me(user: User = Depends(current_user)) -> UserOut:
    return user_out(user)

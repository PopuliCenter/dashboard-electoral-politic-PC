"""Titik masuk FastAPI."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    # Dokumentasi API memetakan semua endpoint; di luar pengembangan tidak dibuka.
    docs_enabled = settings.app_env == "development"
    app = FastAPI(
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        title=settings.app_name,
        version="0.1.0",
        description=(
            "API dashboard elektoral Populi Center. "
            "Setiap respons hasil pemilu membawa sumber dan status data."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    allowed_origins = set(settings.cors_origin_list)

    @app.middleware("http")
    async def reject_foreign_origin(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Tolak permintaan yang mengubah data dari situs lain (lapisan CSRF kedua).

        Cookie sesi sudah SameSite=Lax. Peramban selalu mengirim Origin pada POST
        lintas situs; permintaan tanpa Origin (curl, test) tidak dibawa cookie
        orang lain, jadi dibiarkan.
        """
        origin = request.headers.get("origin")
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and origin is not None
            and origin not in allowed_origins
        ):
            return JSONResponse(
                status_code=403, content={"detail": "asal permintaan tidak diizinkan"}
            )
        return await call_next(request)

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()

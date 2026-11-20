"""Perakitan router /api/v1.

Semua endpoint data wajib login (T5.1). Hanya /health dan /auth/login yang publik.
"""

from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.api.v1 import auth, electoral, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(electoral.router, dependencies=[Depends(current_user)])

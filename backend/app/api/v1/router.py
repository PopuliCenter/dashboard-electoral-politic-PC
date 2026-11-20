"""Perakitan router /api/v1."""

from fastapi import APIRouter

from app.api.v1 import electoral, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(electoral.router)

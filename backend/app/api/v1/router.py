"""Aggregates every v1 router under the `/api/v1` prefix."""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)

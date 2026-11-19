"""Aggregates every v1 router under the `/api/v1` prefix."""

from fastapi import APIRouter

from app.api.v1 import batches, health, jobs, rankings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(batches.router)
api_router.include_router(rankings.router)

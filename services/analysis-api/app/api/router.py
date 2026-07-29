"""Top-level API router."""

from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.inspection import router as inspection_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.part1 import router as part1_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(inspection_router)
api_router.include_router(metrics_router)
api_router.include_router(part1_router)

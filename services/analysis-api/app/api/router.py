"""Top-level API router."""

from fastapi import APIRouter

from app.api.routes.datasets import router as datasets_router
from app.api.routes.health import router as health_router
from app.api.routes.measurements import router as measurements_router
from app.api.routes.measurement_copilot import router as measurement_copilot_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(datasets_router)
api_router.include_router(measurements_router)
api_router.include_router(measurement_copilot_router)

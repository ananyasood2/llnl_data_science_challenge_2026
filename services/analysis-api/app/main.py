"""FastAPI application factory and process entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Create a configured API instance without scientific side effects."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    application = FastAPI(
        title="Lattice CT Analysis API",
        summary="Orchestration boundary for lattice CT inspection.",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.include_router(api_router)
    artifacts = (
        Path(__file__).resolve().parents[3]
        / "output" / "part2" / "refined_registration_20260728" / "tube_r2"
    )
    application.mount("/assets/part2", StaticFiles(directory=artifacts, check_dir=False), name="part2-assets")
    part1_artifacts = Path(__file__).resolve().parents[3] / "output" / "part1" / "nde_report"
    application.mount("/assets/part1", StaticFiles(directory=part1_artifacts, check_dir=False), name="part1-assets")
    return application


app = create_app()

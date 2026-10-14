from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import models
from app.api import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    current_settings = get_settings()

    application = FastAPI(
        title=current_settings.app_name,
        version="0.1.0",
        debug=current_settings.debug,
        docs_url="/docs" if current_settings.environment != "production" else None,
        redoc_url=None,
    )

    if current_settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=current_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(application)
    application.include_router(api_router, prefix=current_settings.api_v1_prefix)

    media_root = Path(current_settings.media_root)
    media_root.mkdir(parents=True, exist_ok=True)
    application.mount(current_settings.media_url, StaticFiles(directory=media_root), name="media")
    return application


app = create_app()

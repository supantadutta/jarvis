"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.config import get_settings
from app.deps import get_brain

logger = logging.getLogger("jarvis")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    # Create DB schema (SQLite by default). Non-fatal if the DB is unavailable.
    try:
        from app.database import init_db

        init_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB init skipped: %s", exc)
    # Build the Brain once.
    brain = get_brain()
    # Start the Cognitive Processing Engine v2 background worker.
    try:
        await brain.processing_queue.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Processing queue not started: %s", exc)
    logger.info("JARVIS backend ready (env=%s).", settings.environment)

    # Optionally start the cron workflow scheduler.
    if settings.scheduler_enabled:
        try:
            await get_brain().scheduler.start()
            logger.info("Workflow scheduler started.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scheduler not started: %s", exc)

    # Optionally start the Telegram bot.
    bot = None
    if settings.telegram_enabled and settings.telegram_bot_token:
        try:
            from app.telegram.bot import JarvisTelegramBot

            bot = JarvisTelegramBot(get_brain(), settings)
            await bot.start()
            logger.info("Telegram bot started.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram bot not started: %s", exc)

    yield

    try:
        await get_brain().processing_queue.stop()
    except Exception:  # noqa: BLE001
        pass
    if settings.scheduler_enabled:
        try:
            await get_brain().scheduler.stop()
        except Exception:  # noqa: BLE001
            pass
    if bot is not None:
        try:
            await bot.stop()
        except Exception:  # noqa: BLE001
            pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description="Local-first multi-AI personal automation platform.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")

    @app.get("/")
    async def root() -> dict:
        return {"name": settings.app_name, "status": "ok", "docs": "/docs"}

    return app


app = create_app()

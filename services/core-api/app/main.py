"""Application entrypoint with lifespan management.

Creates the FastAPI application, manages startup and shutdown lifecycle,
and wires together all core components in a defined initialization order.

Startup order:
    1. Settings (validated configuration)
    2. DatabaseEngine (connection pool)
    3. Connectivity check (non-fatal — degraded mode if DB unreachable)
    4. Middleware registration
    5. Route registration

Shutdown order:
    Reverse of startup — dispose database engine (30s timeout).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.assignments import router as assignments_router
from app.api.care_events import router as care_events_router
from app.api.consents import router as consents_router
from app.api.deletions import router as deletions_router
from app.api.elders import router as elders_router
from app.api.error_handlers import register_exception_handlers
from app.api.health import router as health_router
from app.api.identity import router as identity_router
from app.api.memories import router as memories_router
from app.api.ready import router as ready_router
from app.api.reports import router as reports_router
from app.api.summaries import router as summaries_router
from app.api.tools import router as tools_router
from app.api.voice_sessions import router as voice_sessions_router
from app.core.config import AppEnv, get_settings
from app.db.engine import DatabaseEngine
from app.db.session import init_db_engine
from app.middleware.logging import RequestLoggerMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Ordered startup and shutdown lifecycle.

    Startup:
        1. Load and validate Settings (fatal if invalid — exit non-zero)
        2. Create DatabaseEngine from settings
        3. Check DB connectivity (non-fatal — degraded mode)
        4. Store engine in app.state + init session dependency
        5. Log ready message

    Shutdown:
        Dispose database engine with 30s timeout.
    """
    # ── Step 1: Load settings ────────────────────────────────────────────────
    # If settings fail to load (e.g., invalid DATABASE_URL), this raises
    # a Pydantic ValidationError which propagates and causes process exit.
    try:
        settings = get_settings()
    except Exception as exc:
        logger.critical(
            "fatal_startup_error",
            extra={
                "component": "Settings",
                "error": str(exc),
            },
        )
        print(f"FATAL: Settings validation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: Create DatabaseEngine ────────────────────────────────────────
    db_engine = DatabaseEngine(settings)

    # ── Step 3: Check DB connectivity (non-fatal) ────────────────────────────
    try:
        connected = await db_engine.check_connectivity()
        if not connected:
            logger.warning(
                "db_startup_degraded",
                extra={
                    "component": "DatabaseEngine",
                    "detail": "Database unreachable at startup — running in degraded mode",
                },
            )
    except Exception as exc:
        logger.warning(
            "db_startup_failed",
            extra={
                "component": "DatabaseEngine",
                "error": str(exc),
                "detail": "Database unreachable at startup — running in degraded mode",
            },
        )
        # db_engine.is_ready remains False → session dependency will 503

    # ── Step 4: Wire engine into app state and session dependency ─────────────
    app.state.db_engine = db_engine
    app.state.settings = settings
    init_db_engine(db_engine)

    # ── Step 5: Log ready message ────────────────────────────────────────────
    logger.info(
        "app_ready",
        extra={
            "host": settings.host,
            "port": settings.port,
            "app_env": settings.app_env.value,
        },
    )

    yield

    # ── Shutdown: dispose engine (reverse order) ─────────────────────────────
    await db_engine.dispose(timeout=30.0)
    logger.info("app_shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    - Title, version from settings
    - OpenAPI docs enabled only in development (404 in production)
    - Registers middleware, routes, and exception handlers
    """
    # Load settings for app construction (title, docs configuration).
    # If this fails, the process should exit fast.
    try:
        settings = get_settings()
    except Exception as exc:
        print(f"FATAL: Settings validation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # In production, disable OpenAPI docs (404 for /docs, /redoc, /openapi.json)
    if settings.app_env == AppEnv.PRODUCTION:
        docs_url = None
        redoc_url = None
        openapi_url = None
    else:
        docs_url = settings.docs_url
        redoc_url = "/redoc"
        openapi_url = "/openapi.json"

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # ── Register middleware (outermost first) ────────────────────────────────
    app.add_middleware(RequestLoggerMiddleware)

    # ── Register routes ──────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(ready_router)
    app.include_router(identity_router)
    app.include_router(elders_router)
    app.include_router(consents_router)
    app.include_router(deletions_router)
    app.include_router(voice_sessions_router)
    app.include_router(care_events_router)
    app.include_router(memories_router)
    app.include_router(summaries_router)
    app.include_router(reports_router)
    app.include_router(assignments_router)
    app.include_router(tools_router)

    # ── Register exception handlers ──────────────────────────────────────────
    register_exception_handlers(app)

    return app


# Module-level app instance used by uvicorn (uvicorn app.main:app)
app = create_app()

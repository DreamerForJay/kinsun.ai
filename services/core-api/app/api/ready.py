"""Readiness endpoint for orchestrators and load balancers.

GET /ready verifies database connectivity via SELECT 1 with a 3-second
timeout. Returns 200 when the database is reachable, 503 otherwise.

No authentication is required. Non-GET methods return 405 (handled by
FastAPI's default method routing since only GET is declared).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.db.engine import DatabaseEngine
from app.db.session import get_db_engine

router = APIRouter()

_CONNECTIVITY_TIMEOUT_SECONDS = 10.0


@router.get("/ready")
async def ready(
    db_engine: DatabaseEngine = Depends(get_db_engine),
) -> JSONResponse:
    """Readiness check — verifies database connectivity.

    Returns:
        200 with {"status": "ready", "database": "connected"} on success.
        503 with {"status": "not_ready", "database": "unavailable"} on failure/timeout.
    """
    try:
        connected = await asyncio.wait_for(
            db_engine.check_connectivity(),
            timeout=_CONNECTIVITY_TIMEOUT_SECONDS,
        )
        if connected:
            return JSONResponse(
                status_code=200,
                content={"status": "ready", "database": "connected"},
            )
    except Exception:
        pass

    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "database": "unavailable"},
    )

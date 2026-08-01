from fastapi import FastAPI

from agent_runtime.api.agent_runs import router as agent_runs_router
from agent_runtime.api.error_handlers import register_exception_handlers
from agent_runtime.api.health import router as health_router
from agent_runtime.middleware.correlation import CorrelationIdMiddleware
from agent_runtime.models.mock_provider import MockModelProvider
from agent_runtime.orchestration.orchestrator import AgentOrchestrator
from agent_runtime.settings import get_settings


def build_provider():
    settings = get_settings()
    provider_key = settings.MODEL_PROVIDER.lower()
    if provider_key == "mock":
        return MockModelProvider()
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.MODEL_PROVIDER}")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Eldercare Agent Runtime", version=settings.API_VERSION)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(agent_runs_router)
    app.state.provider = build_provider()
    app.state.orchestrator = AgentOrchestrator(
        provider=app.state.provider,
        max_steps=settings.MAX_AGENT_DECISIONS,
        agent_version=settings.AGENT_VERSION,
        max_tool_rounds=settings.MAX_TOOL_ROUNDS,
        max_total_tools=settings.MAX_TOTAL_TOOLS,
    )
    return app


app = create_app()

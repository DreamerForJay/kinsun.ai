import logging
from pathlib import Path

from fastapi import FastAPI

from agent_runtime.api.agent_runs import router as agent_runs_router
from agent_runtime.api.error_handlers import register_exception_handlers
from agent_runtime.api.health import router as health_router
from agent_runtime.api.rag_retrievals import router as rag_retrievals_router
from agent_runtime.middleware.correlation import CorrelationIdMiddleware
from agent_runtime.models.bedrock_provider import build_bedrock_model_provider
from agent_runtime.models.mock_provider import MockModelProvider
from agent_runtime.orchestration.orchestrator import AgentOrchestrator
from agent_runtime.rag.models import RagRuntimeSettings
from agent_runtime.rag.retriever import build_retriever
from agent_runtime.settings import get_settings

logger = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def build_provider():
    settings = get_settings()
    provider_key = settings.MODEL_PROVIDER.lower()
    if provider_key == "mock":
        return MockModelProvider()
    if provider_key == "bedrock":
        # Fail at startup rather than degrade to the mock: a companion that
        # silently answers from rules while the operator believes a real model
        # is grounded in the knowledge base is worse than one that will not start.
        if not settings.AWS_REGION or not settings.BEDROCK_TEXT_MODEL_ID:
            raise ValueError("MODEL_PROVIDER=bedrock requires AWS_REGION and BEDROCK_TEXT_MODEL_ID")
        return build_bedrock_model_provider(
            region=settings.AWS_REGION,
            model_id=settings.BEDROCK_TEXT_MODEL_ID,
            max_tokens=settings.BEDROCK_TEXT_MAX_TOKENS,
            temperature=settings.BEDROCK_TEXT_TEMPERATURE,
        )
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.MODEL_PROVIDER}")


def build_configured_rag_retriever():
    """Build staging-only adapters, or leave retrieval explicitly unavailable."""

    settings = get_settings()
    if settings.RAG_MODE.casefold() != "staging":
        return None
    try:
        provider_environment = {
            key: str(value)
            for key, value in {
                "AWS_REGION": settings.AWS_REGION,
                "BEDROCK_EMBEDDING_MODEL_ID": settings.BEDROCK_EMBEDDING_MODEL_ID,
                "BEDROCK_EMBEDDING_DIMENSION": settings.BEDROCK_EMBEDDING_DIMENSION,
                "OPENSEARCH_HOST": settings.OPENSEARCH_HOST,
                "OPENSEARCH_INDEX": settings.OPENSEARCH_INDEX,
                "OPENSEARCH_ALIAS": settings.OPENSEARCH_ALIAS,
                "RAG_MODE": settings.RAG_MODE,
            }.items()
            if value is not None and str(value).strip()
        }
        rag_settings = RagRuntimeSettings.from_config_files(
            embedding_config_path=_resolve_config_path(settings.RAG_EMBEDDING_CONFIG_PATH),
            index_config_path=_resolve_config_path(settings.RAG_OPENSEARCH_INDEX_CONFIG_PATH),
            natural_profile_path=_resolve_config_path(settings.RAG_HYBRID_NATURAL_CONFIG_PATH),
            legal_profile_path=_resolve_config_path(settings.RAG_HYBRID_LEGAL_CONFIG_PATH),
            environ=provider_environment,
        )
        return build_retriever(rag_settings)
    except Exception as exc:
        # Never include provider messages: they can contain endpoint/account details.
        logger.warning(
            "staging_rag_unavailable",
            extra={"exception_type": type(exc).__name__},
        )
        return None


def _resolve_config_path(configured_path: str) -> Path:
    """Resolve an environment-provided path from cwd or the repository root."""

    path = Path(configured_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.is_file():
        return cwd_candidate
    return (REPOSITORY_ROOT / path).resolve()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Eldercare Agent Runtime", version=settings.API_VERSION)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(agent_runs_router)
    app.include_router(rag_retrievals_router)
    app.state.provider = build_provider()
    app.state.orchestrator = AgentOrchestrator(
        provider=app.state.provider,
        max_steps=settings.MAX_AGENT_DECISIONS,
        agent_version=settings.AGENT_VERSION,
        max_tool_rounds=settings.MAX_TOOL_ROUNDS,
        max_total_tools=settings.MAX_TOTAL_TOOLS,
    )
    app.state.rag_retriever = build_configured_rag_retriever()
    return app


app = create_app()

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from agent_runtime.agents.companion.agent import CompanionAgent
from agent_runtime.agents.event_extractor.agent import EventExtractorAgent
from agent_runtime.agents.event_extractor.models import (
    CreateCareEventCandidateRequestV1,
    EventExtractionContext,
)
from agent_runtime.agents.safety_evaluator.evaluator import SafetyEvaluator
from agent_runtime.common.enums import ResultStatus, SafetyDecision
from agent_runtime.common.errors import (
    CoreDependencyError,
    InvalidRequestError,
    StepLimitError,
)
from agent_runtime.context.builder import (
    build_minimal_context_manifest,
    build_rag_context_manifest,
)
from agent_runtime.contracts.models import (
    AgentRunRequest,
    AgentRunResponse,
    ContextManifest,
    SafetyEvaluation,
)
from agent_runtime.core.agent_runs import (
    AgentRunRegistrar,
    CoreAgentRunClientError,
    RegisterAgentRunRequest,
)
from agent_runtime.models.provider import ModelProvider
from agent_runtime.orchestration.fallback import fallback_reply
from agent_runtime.orchestration.loop_controller import LoopController
from agent_runtime.orchestration.rag_integration import (
    RagRetriever,
    is_rag_request,
    retrieval_fallback_safety,
    retrieve_for_agent,
)
from agent_runtime.orchestration.stop_conditions import map_to_status
from agent_runtime.rag.citations import append_citations
from agent_runtime.rag.fallback import failed_response
from agent_runtime.rag.models import RetrievalResponseV1
from agent_runtime.tools.errors import CoreToolClientError
from agent_runtime.tools.executor import ToolExecutor
from agent_runtime.tools.requests import (
    CREATE_EVENT_CANDIDATE_TOOL,
    build_create_event_candidate_request,
)
from agent_runtime.tracing.trace import new_agent_run_id, new_trace_id


class AgentOrchestrator:
    """Bounded orchestrator for companion, retrieval, and one safe Tool write."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        max_steps: int,
        agent_version: str = "0.0.1",
        max_tool_rounds: int = 2,
        max_total_tools: int = 5,
    ) -> None:
        if not agent_version.strip() or len(agent_version) > 64:
            raise ValueError("agent_version must be between 1 and 64 characters")
        if max_tool_rounds < 0 or max_total_tools < 0:
            raise ValueError("Tool limits must not be negative")

        self.provider = provider
        self.max_steps = max_steps
        self.agent_version = agent_version
        self.max_tool_rounds = max_tool_rounds
        self.max_total_tools = max_total_tools
        self.companion = CompanionAgent(provider)
        self.event_extractor = EventExtractorAgent()
        self.safety_evaluator = SafetyEvaluator()

    def select_agent(self, _request: AgentRunRequest) -> str:
        return "companion-agent"

    async def run(
        self,
        request: AgentRunRequest,
        *,
        rag_retriever: RagRetriever | None = None,
        agent_run_registrar: AgentRunRegistrar | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> AgentRunResponse:
        if request.max_steps > self.max_steps:
            raise StepLimitError("max_steps exceeds system limit")

        trace_id = request.trace_id or new_trace_id()
        selected_agent = self.select_agent(request)
        context_manifest = build_minimal_context_manifest(request, selected_agent)

        # The companion decision remains one bounded model step. An optional
        # deterministic candidate write happens only after Safety allows the
        # reply and is capped at one Tool call in this release.
        step_count = 1
        if not LoopController(self.max_steps).can_execute(request.max_steps, step_count):
            raise StepLimitError("max_steps does not allow a single decision step")

        retrieval: RetrievalResponseV1 | None = None
        if is_rag_request(request):
            input_safety = self.safety_evaluator.evaluate(request, "")
            if input_safety.decision == SafetyDecision.ALLOW:
                retrieval = await retrieve_for_agent(request, rag_retriever)
                if retrieval.status != "SUCCESS":
                    safety_result = retrieval_fallback_safety(retrieval)
                    return self._response(
                        request=request,
                        trace_id=trace_id,
                        selected_agent=selected_agent,
                        context_manifest=context_manifest,
                        step_count=step_count,
                        safety_result=safety_result,
                        reply_text=fallback_reply(safety_result, ""),
                    )
                try:
                    context_manifest = build_rag_context_manifest(
                        request,
                        selected_agent,
                        retrieval.results,
                    )
                except ValueError:
                    retrieval = failed_response(request.request_id)
                    safety_result = retrieval_fallback_safety(retrieval)
                    return self._response(
                        request=request,
                        trace_id=trace_id,
                        selected_agent=selected_agent,
                        context_manifest=context_manifest,
                        step_count=step_count,
                        safety_result=safety_result,
                        reply_text=fallback_reply(safety_result, ""),
                    )

        companion_output = (
            await self.companion.run(request, context_manifest, request.language)
        ).reply_text
        safety_result = self.safety_evaluator.evaluate(request, companion_output)

        reply_text = fallback_reply(safety_result, companion_output)
        if retrieval is not None and safety_result.decision == SafetyDecision.ALLOW:
            try:
                reply_text = append_citations(reply_text, retrieval.results)
            except ValueError:
                retrieval = failed_response(request.request_id)
                safety_result = retrieval_fallback_safety(retrieval)
                reply_text = fallback_reply(safety_result, "")

        agent_run_id: str | None = None
        result_status_override: ResultStatus | None = None
        tool_reason_codes: list[str] = []
        if (
            safety_result.decision == SafetyDecision.ALLOW
            and CREATE_EVENT_CANDIDATE_TOOL in request.allowed_tools
        ):
            (
                agent_run_id,
                result_status_override,
                tool_reason_codes,
            ) = await self._execute_event_candidate(
                request=request,
                trace_id=trace_id,
                selected_agent=selected_agent,
                agent_run_registrar=agent_run_registrar,
                tool_executor=tool_executor,
            )

        return self._response(
            request=request,
            trace_id=trace_id,
            selected_agent=selected_agent,
            context_manifest=context_manifest,
            step_count=step_count,
            safety_result=safety_result,
            reply_text=reply_text,
            agent_run_id=agent_run_id,
            result_status_override=result_status_override,
            extra_reason_codes=tool_reason_codes,
        )

    async def _execute_event_candidate(
        self,
        *,
        request: AgentRunRequest,
        trace_id: str,
        selected_agent: str,
        agent_run_registrar: AgentRunRegistrar | None,
        tool_executor: ToolExecutor | None,
    ) -> tuple[str | None, ResultStatus | None, list[str]]:
        session_id = self._parse_uuid(request.session_id, "session_id")
        elder_id = self._parse_uuid(request.elder_id, "elder_id")
        extraction = await self.event_extractor.run(
            request,
            EventExtractionContext(source_id=session_id),
        )
        if not isinstance(extraction, CreateCareEventCandidateRequestV1):
            return None, None, []

        if self.max_tool_rounds < 1 or self.max_total_tools < 1:
            raise StepLimitError("Tool execution is disabled by system limits")
        if agent_run_registrar is None or tool_executor is None:
            raise CoreDependencyError("Core Tool execution is unavailable")

        consent_version = self._parse_consent_version(request.consent_version)
        registration_request = RegisterAgentRunRequest(
            session_id=session_id,
            elder_id=elder_id,
            agent_id=selected_agent,
            agent_version=self.agent_version,
            policy_version=request.policy_version,
            trace_id=trace_id,
        )

        try:
            registration = await agent_run_registrar.register(
                registration_request,
                idempotency_key=self._registration_idempotency_key(
                    request,
                    selected_agent,
                ),
            )
            tool_call_id = uuid5(
                registration.agent_run_id,
                f"{CREATE_EVENT_CANDIDATE_TOOL}:{request.request_id}",
            )
            tool_request = build_create_event_candidate_request(
                candidate=extraction,
                tool_call_id=tool_call_id,
                agent_run_id=registration.agent_run_id,
                elder_id=elder_id,
                consent_version=consent_version,
                policy_version=request.policy_version,
                request_id=request.request_id,
                idempotency_key=f"tool:{tool_call_id}",
            )
            tool_result = await tool_executor.execute(tool_request)
        except (CoreAgentRunClientError, CoreToolClientError):
            raise CoreDependencyError("Core Tool execution is unavailable") from None

        result_status_override = None
        if tool_result.result_status == "BLOCKED":
            result_status_override = ResultStatus.BLOCKED
        elif tool_result.result_status == "FAILED":
            result_status_override = ResultStatus.FAILED

        reason_codes = [tool_result.reason_code] if tool_result.reason_code else []
        return str(registration.agent_run_id), result_status_override, reason_codes

    @staticmethod
    def _parse_uuid(value: str, field: str) -> UUID:
        try:
            return UUID(value)
        except ValueError:
            raise InvalidRequestError(
                f"{field} must be a UUID when Tool execution is requested"
            ) from None

    @staticmethod
    def _parse_consent_version(value: str) -> int:
        if not value.isdecimal():
            raise InvalidRequestError(
                "consent_version must be a positive integer when Tool execution is requested"
            )
        parsed = int(value)
        if parsed < 1:
            raise InvalidRequestError(
                "consent_version must be a positive integer when Tool execution is requested"
            )
        return parsed

    def _registration_idempotency_key(
        self,
        request: AgentRunRequest,
        selected_agent: str,
    ) -> str:
        identity = "|".join(
            (
                request.tenant_id,
                request.request_id,
                request.session_id,
                selected_agent,
                self.agent_version,
            )
        )
        return f"agent-run:{uuid5(NAMESPACE_URL, identity)}"

    @staticmethod
    def _response(
        *,
        request: AgentRunRequest,
        trace_id: str,
        selected_agent: str,
        context_manifest: ContextManifest,
        step_count: int,
        safety_result: SafetyEvaluation,
        reply_text: str,
        agent_run_id: str | None = None,
        result_status_override: ResultStatus | None = None,
        extra_reason_codes: list[str] | None = None,
    ) -> AgentRunResponse:
        reason_codes = list(
            dict.fromkeys(
                [
                    *safety_result.reason_codes,
                    *(extra_reason_codes or []),
                ]
            )
        )
        return AgentRunResponse(
            request_id=request.request_id,
            trace_id=trace_id,
            agent_run_id=agent_run_id or new_agent_run_id(),
            selected_agent=selected_agent,
            reply_text=reply_text,
            reply_language=request.language,
            safety_result=safety_result,
            context_manifest_id=context_manifest.context_manifest_id,
            step_count=step_count,
            result_status=result_status_override or map_to_status(safety_result),
            reason_codes=reason_codes,
        )

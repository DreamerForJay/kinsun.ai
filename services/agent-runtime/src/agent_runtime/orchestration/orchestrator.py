from __future__ import annotations

from agent_runtime.agents.companion.agent import CompanionAgent
from agent_runtime.agents.event_extractor.agent import EventExtractorAgent
from agent_runtime.agents.event_extractor.models import EventExtractionContext
from agent_runtime.agents.safety_evaluator.evaluator import SafetyEvaluator
from agent_runtime.common.enums import SafetyDecision
from agent_runtime.common.errors import StepLimitError
from agent_runtime.context.builder import (
    build_minimal_context_manifest,
    build_rag_context_manifest,
)
from agent_runtime.contracts.models import (
    AgentRunRequest,
    AgentRunResponse,
    ContextManifest,
    EventCandidateProposal,
    SafetyEvaluation,
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
from agent_runtime.tracing.trace import new_agent_run_id, new_trace_id


class AgentOrchestrator:
    """Bounded orchestrator that returns replies and untrusted typed proposals."""

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
    ) -> AgentRunResponse:
        if request.max_steps > self.max_steps:
            raise StepLimitError("max_steps exceeds system limit")

        trace_id = request.trace_id or new_trace_id()
        selected_agent = self.select_agent(request)
        context_manifest = build_minimal_context_manifest(request, selected_agent)

        # The companion decision remains one bounded model step. Proposal
        # extraction is deterministic and cannot write Core domain state.
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

        event_candidate_proposal: EventCandidateProposal | None = None
        if (
            safety_result.decision == SafetyDecision.ALLOW
            and "event_candidate" in request.requested_outputs
        ):
            try:
                extraction = await self.event_extractor.run(
                    request,
                    EventExtractionContext(),
                )
            except ValueError:
                extraction = None
            if isinstance(extraction, EventCandidateProposal):
                event_candidate_proposal = extraction

        return self._response(
            request=request,
            trace_id=trace_id,
            selected_agent=selected_agent,
            context_manifest=context_manifest,
            step_count=step_count,
            safety_result=safety_result,
            reply_text=reply_text,
            event_candidate_proposal=event_candidate_proposal,
        )

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
        event_candidate_proposal: EventCandidateProposal | None = None,
    ) -> AgentRunResponse:
        return AgentRunResponse(
            request_id=request.request_id,
            trace_id=trace_id,
            agent_run_id=request.agent_run_id or new_agent_run_id(),
            selected_agent=selected_agent,
            reply_text=reply_text,
            reply_language=request.language,
            safety_result=safety_result,
            context_manifest_id=context_manifest.context_manifest_id,
            step_count=step_count,
            result_status=map_to_status(safety_result),
            reason_codes=list(dict.fromkeys(safety_result.reason_codes)),
            event_candidate_proposal=event_candidate_proposal,
        )

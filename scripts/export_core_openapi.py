"""Export the implemented Core API surface with external versioned schemas."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_API = ROOT / "services" / "core-api"
sys.path.insert(0, str(CORE_API))
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun",
)
os.environ.setdefault("APP_ENV", "development")

from app.main import create_app  # noqa: E402

MODEL_FILES = {
    "ResolveOnboardingRequest": "domain/ResolveOnboardingRequestV1.json",
    "CreateFamilyInvitationRequest": "domain/CreateFamilyInvitationRequestV1.json",
    "CreateConsentRequest": "domain/CreateConsentRequestV1.json",
    "RevokeConsentRequest": "domain/RevokeConsentRequestV1.json",
    "CreateVoiceSessionRequest": "domain/CreateVoiceSessionRequestV1.json",
    "TransitionVoiceSessionRequest": "domain/TransitionVoiceSessionRequestV1.json",
    "CompanionTurnRequest": "domain/CompanionTurnRequestV1.json",
    "CreateCareEventCandidateRequest": "domain/CreateCareEventCandidateRequestV1.json",
    "ReviewCareEventRequest": "domain/ReviewCareEventRequestV1.json",
    "CreateMemoryCandidateRequest": "domain/CreateMemoryCandidateRequestV1.json",
    "ConfirmMemoryRequest": "domain/ConfirmMemoryRequestV1.json",
    "MemoryDecisionRequest": "domain/MemoryDecisionRequestV1.json",
    "UpdateMemoryRequest": "domain/UpdateMemoryRequestV1.json",
    "CreateSummaryDraftRequest": "domain/CreateSummaryDraftRequestV1.json",
    "ReviewSummaryRequest": "domain/ReviewSummaryRequestV1.json",
    "RebuildSummaryRequest": "domain/RebuildSummaryRequestV1.json",
    "CreateFamilyReportDraftRequest": "domain/CreateFamilyReportDraftRequestV1.json",
    "PublishFamilyReportRequest": "domain/PublishFamilyReportRequestV1.json",
    "WithdrawFamilyReportRequest": "domain/WithdrawFamilyReportRequestV1.json",
    "CreateAssignmentRequest": "domain/CreateCareAssignmentRequestV1.json",
    "AssignmentCommandRequest": "domain/AssignmentCommandRequestV1.json",
    "ToolRequest": "tools/ToolRequestV1.json",
}

SUCCESS_ENVELOPE_BY_OPERATION = {
    "resolve_onboarding_api_v1_onboarding_resolve_post": "ResolveOnboardingEnvelopeV1",
    "create_family_invitation_api_v1_elders__elder_id__family_invitations_post": (
        "FamilyInvitationCreatedEnvelopeV1"
    ),
    "list_family_invitations_api_v1_elders__elder_id__family_invitations_get": (
        "FamilyInvitationListEnvelopeV1"
    ),
    "revoke_family_invitation_api_v1_elders__elder_id__family_invitations__invitation_id__revoke_post": (
        "FamilyInvitationStatusEnvelopeV1"
    ),
    "get_me_api_v1_me_get": "ActorProfileEnvelopeV1",
    "get_authorized_elders_api_v1_me_authorized_elders_get": (
        "AuthorizedElderListEnvelopeV1"
    ),
    "get_elder_api_v1_elders__elder_id__get": "ElderSummaryEnvelopeV1",
    "get_elder_access_context_api_v1_elders__elder_id__access_context_get": (
        "ElderAccessContextEnvelopeV1"
    ),
    "list_consents_api_v1_elders__elder_id__consents_get": "ConsentListEnvelopeV1",
    "create_consents_api_v1_elders__elder_id__consents_post": "ConsentListEnvelopeV1",
    "revoke_consent_api_v1_elders__elder_id__consents__consent_id__revoke_post": (
        "ConsentEnvelopeV1"
    ),
    "get_deletion_request_api_v1_elders__elder_id__deletion_requests__deletion_request_id__get": (
        "DeletionRequestEnvelopeV1"
    ),
    "create_voice_session_api_v1_elders__elder_id__voice_sessions_post": (
        "VoiceSessionEnvelopeV1"
    ),
    "get_voice_session_api_v1_voice_sessions__session_id__get": "VoiceSessionEnvelopeV1",
    "cancel_voice_session_api_v1_voice_sessions__session_id__cancel_post": (
        "VoiceSessionEnvelopeV1"
    ),
    "transition_voice_session_api_v1_internal_voice_sessions__session_id__transition_post": (
        "VoiceSessionEnvelopeV1"
    ),
    "complete_voice_session_api_v1_voice_sessions__session_id__complete_post": (
        "VoiceSessionEnvelopeV1"
    ),
    "create_companion_turn_api_v1_voice_sessions__session_id__companion_turns_post": (
        "CompanionTurnEnvelopeV1"
    ),
    "create_care_event_candidate_api_v1_elders__elder_id__care_event_candidates_post": (
        "CareEventEnvelopeV1"
    ),
    "list_care_events_api_v1_elders__elder_id__care_events_get": "CareEventListEnvelopeV1",
    "get_care_event_api_v1_elders__elder_id__care_events__event_id__get": (
        "CareEventEnvelopeV1"
    ),
    "review_care_event_api_v1_elders__elder_id__care_events__event_id__review_post": (
        "CareEventReviewEnvelopeV1"
    ),
    "create_memory_candidate_api_v1_elders__elder_id__memory_candidates_post": (
        "MemoryEnvelopeV1"
    ),
    "list_memory_candidates_api_v1_elders__elder_id__memory_candidates_get": (
        "MemoryListEnvelopeV1"
    ),
    "list_memories_api_v1_elders__elder_id__memories_get": "MemoryListEnvelopeV1",
    "confirm_memory_api_v1_elders__elder_id__memory_candidates__memory_id__confirm_post": (
        "MemoryEnvelopeV1"
    ),
    "reject_memory_api_v1_elders__elder_id__memory_candidates__memory_id__reject_post": (
        "MemoryEnvelopeV1"
    ),
    "defer_memory_api_v1_elders__elder_id__memory_candidates__memory_id__defer_post": (
        "MemoryEnvelopeV1"
    ),
    "update_memory_api_v1_elders__elder_id__memories__memory_id__patch": "MemoryEnvelopeV1",
    "delete_memory_api_v1_elders__elder_id__memories__memory_id__delete": (
        "MemoryDeletionEnvelopeV1"
    ),
    "create_summary_draft_api_v1_internal_elders__elder_id__summary_drafts_post": (
        "DailySummaryEnvelopeV1"
    ),
    "list_summaries_api_v1_elders__elder_id__summaries_get": "DailySummaryListEnvelopeV1",
    "get_summary_api_v1_elders__elder_id__summaries__summary_id__get": (
        "DailySummaryEnvelopeV1"
    ),
    "review_summary_api_v1_elders__elder_id__summaries__summary_id__review_post": (
        "SummaryReviewEnvelopeV1"
    ),
    "rebuild_summary_api_v1_elders__elder_id__summaries__summary_id__rebuild_post": (
        "DailySummaryEnvelopeV1"
    ),
    "create_family_report_draft_api_v1_internal_elders__elder_id__family_report_drafts_post": (
        "FamilyReportEnvelopeV1"
    ),
    "publish_family_report_api_v1_internal_family_reports__report_id__publish_post": (
        "FamilyReportEnvelopeV1"
    ),
    "withdraw_family_report_api_v1_internal_family_reports__report_id__withdraw_post": (
        "FamilyReportEnvelopeV1"
    ),
    "list_family_reports_api_v1_family_elders__elder_id__reports_get": (
        "FamilyReportListEnvelopeV1"
    ),
    "get_family_report_api_v1_family_reports__report_id__get": "FamilyReportEnvelopeV1",
    "create_assignment_api_v1_internal_home_care_assignments_post": (
        "CareAssignmentEnvelopeV1"
    ),
    "list_assignments_api_v1_home_care_assignments_get": "CareAssignmentListEnvelopeV1",
    "get_assignment_api_v1_home_care_assignments__assignment_id__get": (
        "CareAssignmentEnvelopeV1"
    ),
    "confirm_assignment_api_v1_internal_home_care_assignments__assignment_id__confirm_post": (
        "CareAssignmentEnvelopeV1"
    ),
    "start_assignment_api_v1_home_care_assignments__assignment_id__start_post": (
        "CareAssignmentEnvelopeV1"
    ),
    "complete_assignment_api_v1_home_care_assignments__assignment_id__complete_post": (
        "CareAssignmentEnvelopeV1"
    ),
    "execute_tool_api_v1_internal_tools_execute_post": "ToolResultEnvelopeV1",
}

HTTP_METHODS = {"get", "post", "patch", "delete"}


def replace_model_refs(node: object) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            target = MODEL_FILES.get(name)
            if target:
                node["$ref"] = f"../schemas/{target}"
        for value in node.values():
            replace_model_refs(value)
    elif isinstance(node, list):
        for value in node:
            replace_model_refs(value)


def main() -> None:
    contract_path = ROOT / "contracts" / "openapi" / "core-api.v1.yaml"
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required so the exporter can preserve hand-authored operations"
        ) from exc
    prior = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if not isinstance(prior, dict):
        raise ValueError("Existing Core OpenAPI document must be a mapping")

    document = create_app().openapi()
    document["openapi"] = "3.1.0"
    document["info"] = {
        "title": "kinsun.ai Core API",
        "version": "1.2.0",
        "summary": "Implemented Core Domain, consent, security and outbox APIs.",
        "description": (
            "Current executable Core API contract. Every protected operation "
            "re-evaluates tenant, elder, relationship or assignment scope. "
            "Cognito access tokens authenticate existing actors; the onboarding "
            "resolver separately accepts a verified Cognito ID token and never "
            "treats persona intent as authorization."
        ),
    }
    for path in ("/health", "/ready"):
        if prior.get("paths", {}).get(path):
            document["paths"][path] = prior["paths"][path]

    replace_model_refs(document)
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    for name in MODEL_FILES:
        schemas.pop(name, None)
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)

    components = document["components"]
    components["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Cognito access token. Core verifies signature, issuer, expiry, "
                "token_use=access and client_id, then resolves actor, tenant and "
                "role from live Core database state. Development fake auth requires "
                "the explicit FAKE_AUTH_ENABLED flag."
            ),
        },
        "cognitoIdToken": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Cognito ID token accepted only by onboarding resolution. Core "
                "verifies signature, issuer, expiry, token_use=id, audience and "
                "verified email; claims do not directly grant any role or elder scope."
            ),
        },
    }
    components["responses"] = {
        "Unauthorized": {
            "description": "Authentication required or authenticator unavailable.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "../schemas/common/ErrorEnvelopeV1.json"}
                }
            },
        },
        "Forbidden": {
            "description": "The actor is inactive or its role cannot perform the operation.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "../schemas/common/ErrorEnvelopeV1.json"}
                }
            },
        },
        "NotFoundOrForbidden": {
            "description": "Resource missing or outside live authorization scope.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "../schemas/common/ErrorEnvelopeV1.json"}
                }
            },
        },
        "Conflict": {
            "description": "State, version, or idempotency conflict.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "../schemas/common/ErrorEnvelopeV1.json"}
                }
            },
        },
        "ValidationFailed": {
            "description": "Schema or semantic validation failed.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "../schemas/common/ErrorEnvelopeV1.json"}
                }
            },
        },
        "Unavailable": {
            "description": "Required dependency unavailable.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "../schemas/common/ErrorEnvelopeV1.json"}
                }
            },
        },
    }

    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            operation_id = operation.get("operationId")
            envelope = SUCCESS_ENVELOPE_BY_OPERATION.get(operation_id)
            if envelope:
                for status_code, response in operation["responses"].items():
                    if status_code.startswith("2"):
                        response["content"] = {
                            "application/json": {
                                "schema": {
                                    "$ref": f"../schemas/common/{envelope}.json",
                                }
                            }
                        }
                operation["responses"].pop("422", None)
            if path not in {"/health", "/ready"}:
                operation["security"] = (
                    [{"cognitoIdToken": []}]
                    if path == "/api/v1/onboarding/resolve"
                    else [{"bearerAuth": []}]
                )
                operation["responses"].update(
                    {
                        "401": {"$ref": "#/components/responses/Unauthorized"},
                        "403": {"$ref": "#/components/responses/Forbidden"},
                        "404": {"$ref": "#/components/responses/NotFoundOrForbidden"},
                        "409": {"$ref": "#/components/responses/Conflict"},
                        "422": {"$ref": "#/components/responses/ValidationFailed"},
                        "503": {"$ref": "#/components/responses/Unavailable"},
                    }
                )
            else:
                operation["security"] = []

    document["security"] = [{"bearerAuth": []}]
    contract_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {contract_path.relative_to(ROOT)} with {len(document['paths'])} paths")


if __name__ == "__main__":
    main()

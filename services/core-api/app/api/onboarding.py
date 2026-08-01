"""Server-to-server Cognito onboarding callback resolution."""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth.cognito import CognitoTokenVerifier, VerifiedCognitoIdentity
from app.api.responses import get_correlation_id, success
from app.core.exceptions import AuthenticationError, ValidationError
from app.db.session import get_db_session
from app.middleware.auth import get_cognito_token_verifier
from app.schemas.onboarding import (
    ElderOnboardingRequest,
    ResolveOnboardingRequest,
    ResolveOnboardingResponse,
)
from app.services.family_invitation_service import FamilyInvitationService
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec
from app.services.onboarding_service import OnboardingService
from app.services.service_dependencies import get_family_invitation_token_codec

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])
_AUTHENTICATION_REQUIRED = "Authentication required"


async def verified_onboarding_identity(
    request: Request,
    verifier: CognitoTokenVerifier = Depends(get_cognito_token_verifier),
) -> VerifiedCognitoIdentity:
    """Verify exactly one Cognito ID token without granting a Core role."""
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    scheme, separator, credential = values[0].partition(" ")
    if (
        separator != " "
        or scheme.casefold() != "bearer"
        or not credential
        or any(character.isspace() for character in credential)
    ):
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    try:
        return await verifier.verify_id_token(credential)
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED) from exc


@router.post("/resolve", status_code=status.HTTP_200_OK)
async def resolve_onboarding(
    request: ResolveOnboardingRequest,
    identity: VerifiedCognitoIdentity = Depends(verified_onboarding_identity),
    session: AsyncSession = Depends(get_db_session),
    codec: FamilyInvitationTokenCodec = Depends(get_family_invitation_token_codec),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    """Resolve a BFF callback intent into formal Core database state."""
    trace_id = get_correlation_id()
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 160:
            raise ValidationError(
                details=[
                    {
                        "field": "Idempotency-Key",
                        "reason": "A non-empty key of at most 160 characters is required",
                    }
                ]
            )
    operation_key = (
        idempotency_key or hashlib.sha256(f"onboarding:{identity.subject}".encode()).hexdigest()
    )

    if request.intent == "ELDER":
        if request.invitation_code is not None:
            raise ValidationError(
                details=[
                    {
                        "field": "invitation_code",
                        "reason": "invitation_code is only valid for FAMILY onboarding",
                    }
                ]
            )
        email = identity.email or ""
        display_name = identity.display_name or email.partition("@")[0] or "長者"
        result = await OnboardingService(session).onboard_elder(
            identity=identity,
            request=ElderOnboardingRequest(display_name=display_name),
            trace_id=trace_id,
            idempotency_key=operation_key,
        )
        response = ResolveOnboardingResponse(
            intent="ELDER",
            actor_id=result.actor_id,
            tenant_id=result.tenant_id,
            elder_id=result.elder_id,
            status="ACTIVE",
            replayed=result.replayed,
        )
    else:
        if request.invitation_code is None:
            raise ValidationError(
                details=[
                    {
                        "field": "invitation_code",
                        "reason": "invitation_code is required for FAMILY onboarding",
                    }
                ]
            )
        result = await FamilyInvitationService(session, codec).redeem(
            identity=identity,
            invitation_code=request.invitation_code,
            trace_id=trace_id,
            idempotency_key=operation_key,
        )
        response = ResolveOnboardingResponse(
            intent="FAMILY",
            actor_id=result.actor_id,
            tenant_id=result.tenant_id,
            elder_id=result.elder_id,
            status="REDEEMED",
            replayed=result.replayed,
        )
    return success(response.model_dump(mode="json"))

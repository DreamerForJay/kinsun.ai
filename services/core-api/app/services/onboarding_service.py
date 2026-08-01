"""Atomic, Google-backed elder onboarding into a personal household."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth.cognito import VerifiedCognitoIdentity
from app.core.exceptions import AuthenticationError, ConflictError
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant
from app.schemas.onboarding import ElderOnboardingRequest, ElderOnboardingResponse

_AUTHENTICATION_REQUIRED = "Authentication required"


class OnboardingService:
    """Create the actor, tenant, membership and elder in one transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def onboard_elder(
        self,
        *,
        identity: VerifiedCognitoIdentity,
        request: ElderOnboardingRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> ElderOnboardingResponse:
        email = self._verified_email(identity)

        # There is no actor row to lock on a first request.  A transaction-level
        # advisory lock serializes concurrent callbacks for the same verified
        # Cognito subject without persisting the subject outside Actor.
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 0))"),
            {"subject": identity.subject},
        )

        existing = await self._session.scalar(
            select(Actor).where(Actor.cognito_sub == identity.subject)
        )
        if existing is not None:
            return await self._existing_elder(existing, datetime.now(UTC))

        email_owner = await self._session.scalar(
            select(Actor).where(func.lower(Actor.email) == email)
        )
        if email_owner is not None:
            # Never bind a newly authenticated subject to a pre-existing actor
            # merely because the e-mail addresses happen to match.
            raise ConflictError("This identity requires administrator review")

        now = datetime.now(UTC)
        display_name = request.display_name
        tenant = Tenant(
            tenant_type="HOUSEHOLD",
            name=f"{display_name}的家庭",
            status="ACTIVE",
            timezone=request.timezone,
        )
        actor = Actor(
            actor_type="ELDER",
            cognito_sub=identity.subject,
            display_name=display_name,
            email=email,
            status="ACTIVE",
        )
        self._session.add_all((tenant, actor))
        await self._session.flush()

        elder = Elder(
            tenant_id=tenant.id,
            actor_id=actor.id,
            display_name=display_name,
            primary_care_setting="INDEPENDENT",
            status="ACTIVE",
            preferred_language=request.preferred_language,
            preferred_name=request.preferred_name,
            response_length_preference=request.response_length_preference,
            timezone=request.timezone,
        )
        membership = ActorTenantMembership(
            actor_id=actor.id,
            tenant_id=tenant.id,
            care_unit_id=None,
            role_code="ELDER",
            status="ACTIVE",
            effective_from=now,
        )
        self._session.add_all((elder, membership))
        await self._session.flush()

        await write_outbox_entry(
            self._session,
            event_type="elder.onboarded.v1",
            aggregate_type="elder",
            aggregate_id=elder.id,
            tenant_id=tenant.id,
            elder_id=elder.id,
            actor_id=actor.id,
            payload={
                "elder_id": str(elder.id),
                "actor_id": str(actor.id),
                "tenant_id": str(tenant.id),
                "registration_status": "ACTIVE",
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return ElderOnboardingResponse(
            actor_id=actor.id,
            tenant_id=tenant.id,
            elder_id=elder.id,
            replayed=False,
        )

    @staticmethod
    def _verified_email(identity: VerifiedCognitoIdentity) -> str:
        if not identity.email_verified or identity.email is None:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        email = identity.email.strip().casefold()
        if not email:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        return email

    async def _existing_elder(
        self,
        actor: Actor,
        now: datetime,
    ) -> ElderOnboardingResponse:
        if actor.actor_type != "ELDER" or actor.status != "ACTIVE":
            raise ConflictError("This identity is already registered with another role")
        elders = list(
            (
                await self._session.execute(
                    select(Elder)
                    .join(Tenant, Tenant.id == Elder.tenant_id)
                    .where(
                        Elder.actor_id == actor.id,
                        Elder.status == "ACTIVE",
                        Tenant.status == "ACTIVE",
                        Tenant.tenant_type == "HOUSEHOLD",
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(elders) != 1:
            raise ConflictError("Existing registration requires administrator review")
        elder = elders[0]
        membership_count = await self._session.scalar(
            select(func.count())
            .select_from(ActorTenantMembership)
            .where(
                ActorTenantMembership.actor_id == actor.id,
                ActorTenantMembership.tenant_id == elder.tenant_id,
                ActorTenantMembership.care_unit_id.is_(None),
                ActorTenantMembership.role_code == "ELDER",
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= now,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    now < ActorTenantMembership.effective_to,
                ),
            )
        )
        if membership_count != 1:
            raise ConflictError("Existing registration requires administrator review")
        return ElderOnboardingResponse(
            actor_id=actor.id,
            tenant_id=elder.tenant_id,
            elder_id=elder.id,
            replayed=True,
        )

"""Consent-bound, one-time family invitation lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth.cognito import VerifiedCognitoIdentity
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.care_relationship import CareRelationship
from app.models.elder import Elder
from app.models.family_invitation import FamilyInvitation
from app.models.membership import ActorTenantMembership
from app.models.report import FamilyRelationship
from app.models.tenant import Tenant
from app.repositories.consent_repo import ConsentRepository
from app.repositories.family_invitation_repo import FamilyInvitationRepository
from app.schemas.family_invitation import (
    CreateFamilyInvitationRequest,
    FamilyInvitationCreatedResponse,
    FamilyInvitationListResponse,
    FamilyInvitationRedeemedResponse,
    FamilyInvitationStatusResponse,
)
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec

_AUTHENTICATION_REQUIRED = "Authentication required"
_FAMILY_REPORT_ACTIONS = ["family_report:read"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FamilyInvitationService:
    """Issue and redeem family access without deriving authorization from JWT claims."""

    def __init__(
        self,
        session: AsyncSession,
        codec: FamilyInvitationTokenCodec,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session = session
        self._codec = codec
        self._now = now
        self._invitations = FamilyInvitationRepository(session)

    async def create(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
        request: CreateFamilyInvitationRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> FamilyInvitationCreatedResponse:
        elder = await self._require_elder_self(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        now = self._now()
        consent = await ConsentRepository(self._session, tenant_id).get_active(
            elder_id=elder.id,
            purpose_code="FAMILY_SHARING",
            current_time=now,
        )
        if consent is None:
            raise ConflictError(
                "Family sharing consent must be active before issuing an invitation"
            )
        consent_scopes = set((consent.scope or {}).get("share_scopes", []))
        if not set(request.share_scope).issubset(consent_scopes):
            raise ConflictError("Invitation scope exceeds the active family sharing consent")

        code, token_hash = self._codec.generate()
        invitee_email_hmac = (
            self._codec.hash_email(request.invitee_email) if request.invitee_email else None
        )
        invitation = FamilyInvitation(
            tenant_id=tenant_id,
            elder_id=elder_id,
            issued_by_actor_id=actor_id,
            invitee_email_hmac=invitee_email_hmac,
            token_hash=token_hash,
            share_scope=list(request.share_scope),
            consent_id=consent.id,
            status="ISSUED",
            expires_at=now + timedelta(hours=request.expires_in_hours),
            attempt_count=0,
            max_attempts=5,
        )
        self._invitations.add(invitation)
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="family_invitation.issued.v1",
            aggregate_type="family_invitation",
            aggregate_id=invitation.id,
            aggregate_version=invitation.version,
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose="FAMILY_SHARING",
            consent_version=consent.version,
            payload={
                "invitation_id": str(invitation.id),
                "elder_id": str(elder_id),
                "status": invitation.status,
                "expires_at": invitation.expires_at.isoformat(),
                "share_scope": list(invitation.share_scope),
                "recipient_bound": invitation.invitee_email_hmac is not None,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return FamilyInvitationCreatedResponse(
            invitation_id=invitation.id,
            invitation_code=code,
            share_scope=invitation.share_scope,
            expires_at=invitation.expires_at,
        )

    async def redeem(
        self,
        *,
        identity: VerifiedCognitoIdentity,
        invitation_code: str,
        trace_id: str,
        idempotency_key: str,
    ) -> FamilyInvitationRedeemedResponse:
        email = self._verified_email(identity)
        token_hash = self._codec.hash_code(invitation_code)
        invitation = await self._invitations.get_by_token_hash_for_update(token_hash)
        if invitation is None:
            self._invalid_invitation()

        # Callback retries after a successful database commit are safe for the
        # same verified Cognito subject, while every other identity sees the
        # same generic unavailable response.
        if invitation.status == "REDEEMED":
            return await self._replayed_redemption(invitation, identity.subject)
        now = self._now()
        if invitation.status != "ISSUED" or now >= invitation.expires_at:
            self._invalid_invitation()
        if invitation.invitee_email_hmac is not None and not self._codec.matches(
            invitation.invitee_email_hmac,
            self._codec.hash_email(email),
        ):
            self._invalid_invitation()

        # Serialize two simultaneous invitation redemptions for one Cognito
        # identity before checking e-mail uniqueness or memberships.
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 0))"),
            {"subject": identity.subject},
        )
        elder, consent = await self._require_live_invitation_authority(invitation, now)
        actor = await self._resolve_or_create_family_actor(identity, email)
        membership = await self._ensure_single_household_membership(
            actor=actor,
            tenant_id=invitation.tenant_id,
            now=now,
        )
        relationship = await self._ensure_care_relationship(
            actor_id=actor.id,
            invitation=invitation,
            now=now,
        )
        family_relationship = await self._ensure_family_relationship(
            actor_id=actor.id,
            invitation=invitation,
            now=now,
        )

        invitation.status = "REDEEMED"
        invitation.redeemed_by_actor_id = actor.id
        invitation.redeemed_at = now
        invitation.version += 1
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="family_invitation.redeemed.v1",
            aggregate_type="family_invitation",
            aggregate_id=invitation.id,
            aggregate_version=invitation.version,
            tenant_id=invitation.tenant_id,
            elder_id=elder.id,
            actor_id=actor.id,
            purpose="FAMILY_SHARING",
            consent_version=consent.version,
            payload={
                "invitation_id": str(invitation.id),
                "elder_id": str(elder.id),
                "family_actor_id": str(actor.id),
                "membership_id": str(membership.id),
                "relationship_id": str(relationship.id),
                "family_relationship_id": str(family_relationship.id),
                "status": invitation.status,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return FamilyInvitationRedeemedResponse(
            invitation_id=invitation.id,
            actor_id=actor.id,
            tenant_id=invitation.tenant_id,
            elder_id=invitation.elder_id,
            relationship_id=relationship.id,
            family_relationship_id=family_relationship.id,
        )

    async def list_for_elder(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
    ) -> FamilyInvitationListResponse:
        await self._require_elder_self(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        now = self._now()
        invitations = await self._invitations.list_for_elder(
            tenant_id=tenant_id,
            elder_id=elder_id,
        )
        return FamilyInvitationListResponse(
            items=[self._status_response(item, now) for item in invitations]
        )

    async def revoke(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        invitation_id: UUID,
        actor_id: UUID,
        actor_role: str,
        trace_id: str,
        idempotency_key: str,
    ) -> FamilyInvitationStatusResponse:
        await self._require_elder_self(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        invitation = await self._invitations.get_for_elder(
            invitation_id=invitation_id,
            tenant_id=tenant_id,
            elder_id=elder_id,
            for_update=True,
        )
        if invitation is None:
            raise NotFoundError("Resource not found")
        now = self._now()
        if invitation.status == "REVOKED":
            return self._status_response(invitation, now)
        if invitation.status != "ISSUED" or now >= invitation.expires_at:
            raise ConflictError("Only an active invitation can be revoked")
        invitation.status = "REVOKED"
        invitation.revoked_at = now
        invitation.version += 1
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="family_invitation.revoked.v1",
            aggregate_type="family_invitation",
            aggregate_id=invitation.id,
            aggregate_version=invitation.version,
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose="FAMILY_SHARING",
            payload={
                "invitation_id": str(invitation.id),
                "elder_id": str(elder_id),
                "status": invitation.status,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return self._status_response(invitation, now)

    async def _require_elder_self(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
    ) -> Elder:
        if actor_role != "ELDER":
            raise NotFoundError("Resource not found")
        elder = await self._session.scalar(
            select(Elder).where(
                Elder.id == elder_id,
                Elder.tenant_id == tenant_id,
                Elder.actor_id == actor_id,
                Elder.status == "ACTIVE",
            )
        )
        if elder is None:
            raise NotFoundError("Resource not found")
        return elder

    async def _require_live_invitation_authority(
        self,
        invitation: FamilyInvitation,
        now: datetime,
    ):
        elder = await self._session.scalar(
            select(Elder)
            .join(Tenant, Tenant.id == Elder.tenant_id)
            .where(
                Elder.id == invitation.elder_id,
                Elder.tenant_id == invitation.tenant_id,
                Elder.status == "ACTIVE",
                Tenant.status == "ACTIVE",
                Tenant.tenant_type == "HOUSEHOLD",
            )
        )
        if elder is None or elder.actor_id != invitation.issued_by_actor_id:
            self._invalid_invitation()
        consent = await ConsentRepository(self._session, invitation.tenant_id).get_active(
            elder_id=invitation.elder_id,
            purpose_code="FAMILY_SHARING",
            current_time=now,
        )
        if consent is None or consent.id != invitation.consent_id:
            self._invalid_invitation()
        consent_scopes = set((consent.scope or {}).get("share_scopes", []))
        if not set(invitation.share_scope).issubset(consent_scopes):
            self._invalid_invitation()
        return elder, consent

    async def _resolve_or_create_family_actor(
        self,
        identity: VerifiedCognitoIdentity,
        email: str,
    ) -> Actor:
        actor = await self._session.scalar(
            select(Actor).where(Actor.cognito_sub == identity.subject)
        )
        if actor is not None:
            if actor.actor_type != "FAMILY_MEMBER" or actor.status != "ACTIVE":
                raise ConflictError("This identity is already registered with another role")
            return actor
        email_owner = await self._session.scalar(
            select(Actor).where(func.lower(Actor.email) == email)
        )
        if email_owner is not None:
            raise ConflictError("This identity requires administrator review")
        display_name = identity.display_name or email.partition("@")[0]
        actor = Actor(
            actor_type="FAMILY_MEMBER",
            cognito_sub=identity.subject,
            display_name=display_name[:120],
            email=email,
            status="ACTIVE",
        )
        self._session.add(actor)
        await self._session.flush()
        return actor

    async def _ensure_single_household_membership(
        self,
        *,
        actor: Actor,
        tenant_id: UUID,
        now: datetime,
    ) -> ActorTenantMembership:
        active_memberships = list(
            (
                await self._session.execute(
                    select(ActorTenantMembership).where(
                        ActorTenantMembership.actor_id == actor.id,
                        ActorTenantMembership.care_unit_id.is_(None),
                        ActorTenantMembership.status == "ACTIVE",
                        ActorTenantMembership.effective_from <= now,
                        or_(
                            ActorTenantMembership.effective_to.is_(None),
                            now < ActorTenantMembership.effective_to,
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        if active_memberships:
            if len(active_memberships) != 1:
                raise ConflictError("Family identity has ambiguous tenant membership")
            membership = active_memberships[0]
            if membership.tenant_id != tenant_id or membership.role_code != "FAMILY_MEMBER":
                raise ConflictError("Family identity already belongs to another household")
            return membership

        historical = await self._session.scalar(
            select(ActorTenantMembership).where(
                ActorTenantMembership.actor_id == actor.id,
                ActorTenantMembership.tenant_id == tenant_id,
                ActorTenantMembership.care_unit_id.is_(None),
                ActorTenantMembership.role_code == "FAMILY_MEMBER",
            )
        )
        if historical is not None:
            historical.status = "ACTIVE"
            historical.effective_from = now
            historical.effective_to = None
            await self._session.flush()
            return historical

        membership = ActorTenantMembership(
            actor_id=actor.id,
            tenant_id=tenant_id,
            care_unit_id=None,
            role_code="FAMILY_MEMBER",
            status="ACTIVE",
            effective_from=now,
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def _ensure_care_relationship(
        self,
        *,
        actor_id: UUID,
        invitation: FamilyInvitation,
        now: datetime,
    ) -> CareRelationship:
        relationship = await self._session.scalar(
            select(CareRelationship)
            .where(
                CareRelationship.actor_id == actor_id,
                CareRelationship.elder_id == invitation.elder_id,
                CareRelationship.tenant_id == invitation.tenant_id,
                CareRelationship.relationship_type == "FAMILY_SHARE",
                CareRelationship.status == "ACTIVE",
                CareRelationship.effective_from <= now,
                or_(
                    CareRelationship.effective_to.is_(None),
                    now < CareRelationship.effective_to,
                ),
            )
            .order_by(CareRelationship.created_at.desc())
            .limit(1)
        )
        if relationship is not None:
            relationship.scope = list(_FAMILY_REPORT_ACTIONS)
            return relationship
        relationship = CareRelationship(
            actor_id=actor_id,
            elder_id=invitation.elder_id,
            tenant_id=invitation.tenant_id,
            care_unit_id=None,
            relationship_type="FAMILY_SHARE",
            scope=list(_FAMILY_REPORT_ACTIONS),
            status="ACTIVE",
            effective_from=now,
        )
        self._session.add(relationship)
        await self._session.flush()
        return relationship

    async def _ensure_family_relationship(
        self,
        *,
        actor_id: UUID,
        invitation: FamilyInvitation,
        now: datetime,
    ) -> FamilyRelationship:
        relationship = await self._session.scalar(
            select(FamilyRelationship).where(
                FamilyRelationship.elder_id == invitation.elder_id,
                FamilyRelationship.family_actor_id == actor_id,
                FamilyRelationship.consent_id == invitation.consent_id,
            )
        )
        if relationship is None:
            relationship = FamilyRelationship(
                elder_id=invitation.elder_id,
                family_actor_id=actor_id,
                share_scope=list(invitation.share_scope),
                status="ACTIVE",
                effective_from=now,
                consent_id=invitation.consent_id,
            )
            self._session.add(relationship)
            await self._session.flush()
            return relationship
        relationship.share_scope = list(invitation.share_scope)
        relationship.status = "ACTIVE"
        relationship.effective_from = now
        relationship.effective_to = None
        return relationship

    async def _replayed_redemption(
        self,
        invitation: FamilyInvitation,
        subject: str,
    ) -> FamilyInvitationRedeemedResponse:
        actor = await self._session.scalar(select(Actor).where(Actor.cognito_sub == subject))
        if actor is None or actor.id != invitation.redeemed_by_actor_id:
            self._invalid_invitation()
        relationship = await self._session.scalar(
            select(CareRelationship)
            .where(
                CareRelationship.actor_id == actor.id,
                CareRelationship.elder_id == invitation.elder_id,
                CareRelationship.tenant_id == invitation.tenant_id,
                CareRelationship.relationship_type == "FAMILY_SHARE",
            )
            .order_by(CareRelationship.created_at.desc())
            .limit(1)
        )
        family_relationship = await self._session.scalar(
            select(FamilyRelationship).where(
                FamilyRelationship.elder_id == invitation.elder_id,
                FamilyRelationship.family_actor_id == actor.id,
                FamilyRelationship.consent_id == invitation.consent_id,
            )
        )
        if relationship is None or family_relationship is None:
            raise ConflictError("Existing invitation redemption requires administrator review")
        return FamilyInvitationRedeemedResponse(
            invitation_id=invitation.id,
            actor_id=actor.id,
            tenant_id=invitation.tenant_id,
            elder_id=invitation.elder_id,
            relationship_id=relationship.id,
            family_relationship_id=family_relationship.id,
            replayed=True,
        )

    @staticmethod
    def _verified_email(identity: VerifiedCognitoIdentity) -> str:
        if not identity.email_verified or identity.email is None:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        email = identity.email.strip().casefold()
        if not email:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        return email

    @staticmethod
    def _invalid_invitation() -> None:
        raise ValidationError(
            details=[
                {
                    "field": "invitation_code",
                    "reason": "Invitation code is unavailable",
                }
            ]
        )

    @staticmethod
    def _status_response(
        invitation: FamilyInvitation,
        now: datetime,
    ) -> FamilyInvitationStatusResponse:
        status = invitation.status
        if status == "ISSUED" and now >= invitation.expires_at:
            status = "EXPIRED"
        return FamilyInvitationStatusResponse(
            invitation_id=invitation.id,
            status=status,
            share_scope=invitation.share_scope,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )

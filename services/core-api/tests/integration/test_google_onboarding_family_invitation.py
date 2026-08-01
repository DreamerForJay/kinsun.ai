"""Real PostgreSQL coverage for the Google household and invitation slice."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from app.adapters.auth.cognito import VerifiedCognitoIdentity
from app.core.exceptions import ValidationError
from app.models.actor import Actor
from app.models.care_relationship import CareRelationship
from app.models.consent import ConsentGrant
from app.models.family_invitation import FamilyInvitation
from app.models.membership import ActorTenantMembership
from app.models.policy import PolicyRegistry
from app.models.report import FamilyRelationship
from app.models.tenant import Tenant
from app.schemas.family_invitation import CreateFamilyInvitationRequest
from app.schemas.onboarding import ElderOnboardingRequest
from app.services.family_invitation_service import FamilyInvitationService
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec
from app.services.onboarding_service import OnboardingService


async def test_household_onboarding_and_one_time_family_redemption_are_atomic(db_session) -> None:
    elder_identity = VerifiedCognitoIdentity(
        subject="google-elder-integration",
        email="elder.integration@example.test",
        email_verified=True,
        display_name="整合測試長者",
    )
    onboarding = await OnboardingService(db_session).onboard_elder(
        identity=elder_identity,
        request=ElderOnboardingRequest(display_name="整合測試長者"),
        trace_id="trace-google-onboarding-integration",
        idempotency_key="idem-google-onboarding-integration",
    )

    tenant = await db_session.get(Tenant, onboarding.tenant_id)
    assert tenant is not None and tenant.tenant_type == "HOUSEHOLD"

    policy = PolicyRegistry(
        owner_tenant_id=onboarding.tenant_id,
        policy_code="family-sharing-integration",
        policy_type="CONSENT",
        version="integration-v1",
        status="ACTIVE",
        policy_payload={"synthetic": True},
        effective_from=datetime.now(UTC),
        approved_by_actor_id=onboarding.actor_id,
    )
    db_session.add(policy)
    await db_session.flush()
    consent = ConsentGrant(
        elder_id=onboarding.elder_id,
        purpose_code="FAMILY_SHARING",
        status="GRANTED",
        version=1,
        scope={"share_scopes": ["REPORT_DAILY", "REPORT_WEEKLY"]},
        granted_by_actor_id=onboarding.actor_id,
        policy_id=policy.id,
        granted_at=datetime.now(UTC),
        effective_at=datetime.now(UTC),
    )
    db_session.add(consent)
    await db_session.flush()

    codec = FamilyInvitationTokenCodec("integration-family-invitation-secret-32-bytes")
    service = FamilyInvitationService(db_session, codec)
    created = await service.create(
        tenant_id=onboarding.tenant_id,
        elder_id=onboarding.elder_id,
        actor_id=onboarding.actor_id,
        actor_role="ELDER",
        request=CreateFamilyInvitationRequest(
            invitee_email="family.integration@example.test",
            share_scope=["REPORT_DAILY", "REPORT_WEEKLY"],
        ),
        trace_id="trace-family-invitation-integration",
        idempotency_key="idem-family-invitation-integration",
    )
    invitation = await db_session.get(FamilyInvitation, created.invitation_id)
    assert invitation is not None
    assert invitation.token_hash == codec.hash_code(created.invitation_code)
    assert created.invitation_code not in invitation.token_hash
    assert invitation.invitee_email_hmac != "family.integration@example.test"

    family_identity = VerifiedCognitoIdentity(
        subject="google-family-integration",
        email="family.integration@example.test",
        email_verified=True,
        display_name="整合測試家屬",
    )
    redeemed = await service.redeem(
        identity=family_identity,
        invitation_code=created.invitation_code,
        trace_id="trace-family-redemption-integration",
        idempotency_key="idem-family-redemption-integration",
    )
    await db_session.flush()

    family_actor = await db_session.get(Actor, redeemed.actor_id)
    membership = await db_session.scalar(
        select(ActorTenantMembership).where(
            ActorTenantMembership.actor_id == redeemed.actor_id,
            ActorTenantMembership.tenant_id == onboarding.tenant_id,
            ActorTenantMembership.role_code == "FAMILY_MEMBER",
            ActorTenantMembership.status == "ACTIVE",
        )
    )
    care_relationship = await db_session.get(CareRelationship, redeemed.relationship_id)
    family_relationship = await db_session.get(
        FamilyRelationship,
        redeemed.family_relationship_id,
    )
    assert family_actor is not None and family_actor.actor_type == "FAMILY_MEMBER"
    assert membership is not None
    assert care_relationship is not None
    assert care_relationship.scope == ["family_report:read"]
    assert family_relationship is not None
    assert family_relationship.consent_id == consent.id
    assert family_relationship.share_scope == ["REPORT_DAILY", "REPORT_WEEKLY"]
    assert invitation.status == "REDEEMED"
    assert invitation.redeemed_by_actor_id == redeemed.actor_id

    replay = await service.redeem(
        identity=family_identity,
        invitation_code=created.invitation_code,
        trace_id="trace-family-redemption-replay",
        idempotency_key="idem-family-redemption-replay",
    )
    assert replay.replayed is True
    assert replay.actor_id == redeemed.actor_id

    with pytest.raises(ValidationError, match="Validation failed"):
        await service.redeem(
            identity=VerifiedCognitoIdentity(
                subject="google-family-attacker",
                email="attacker.integration@example.test",
                email_verified=True,
            ),
            invitation_code=created.invitation_code,
            trace_id="trace-family-redemption-attacker",
            idempotency_key="idem-family-redemption-attacker",
        )


async def test_migration_exposes_household_enum_and_hash_only_invitation_table(db_session) -> None:
    enum_exists = await db_session.scalar(
        text(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'eldercare_ai' "
            "AND t.typname = 'tenant_type_enum' "
            "AND e.enumlabel = 'HOUSEHOLD')"
        )
    )
    plaintext_column_count = await db_session.scalar(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'eldercare_ai' "
            "AND table_name = 'family_invitation' "
            "AND column_name IN ('invitation_code', 'token', 'plaintext_code')"
        )
    )
    hash_column_count = await db_session.scalar(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'eldercare_ai' "
            "AND table_name = 'family_invitation' "
            "AND column_name = 'token_hash'"
        )
    )
    assert enum_exists is True
    assert plaintext_column_count == 0
    assert hash_column_count == 1

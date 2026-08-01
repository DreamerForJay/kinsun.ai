"""Unit tests for consent-bound, one-time family invitation redemption."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.adapters.auth.cognito import VerifiedCognitoIdentity
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.actor import Actor
from app.models.care_relationship import CareRelationship
from app.models.family_invitation import FamilyInvitation
from app.models.membership import ActorTenantMembership
from app.models.report import FamilyRelationship
from app.schemas.family_invitation import CreateFamilyInvitationRequest
from app.services.family_invitation_service import FamilyInvitationService
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
SECRET = "unit-test-family-invitation-secret-32-bytes"
VALID_CODE = "ABCD-2345-EFGH-6789"


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _Result:
    def __init__(
        self,
        *,
        single: object | None = None,
        rows: list[object] | None = None,
    ) -> None:
        self._single = single
        self._rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self._single

    def scalars(self) -> _ScalarRows:
        return _ScalarRows(self._rows)


class _FakeSession:
    def __init__(
        self,
        *,
        scalar_results: list[object | None] | None = None,
        execute_results: list[object] | None = None,
    ) -> None:
        self._scalar_results = deque(scalar_results or [])
        self._execute_results = deque(execute_results or [])
        self.added: list[object] = []
        self.execute_calls: list[tuple[object, object | None]] = []

    async def execute(self, statement: object, parameters: object | None = None) -> object:
        self.execute_calls.append((statement, parameters))
        return self._execute_results.popleft() if self._execute_results else _Result()

    async def scalar(self, statement: object) -> object | None:
        del statement
        return self._scalar_results.popleft()

    def add(self, entity: object) -> None:
        self.added.append(entity)

    async def flush(self) -> None:
        for entity in self.added:
            if getattr(entity, "id", None) is None:
                entity.id = uuid4()
            if getattr(entity, "created_at", None) is None:
                entity.created_at = NOW
            if getattr(entity, "updated_at", None) is None:
                entity.updated_at = NOW
            if isinstance(entity, FamilyInvitation) and getattr(entity, "version", None) is None:
                entity.version = 1


def _identity(
    subject: str = "family-google-subject",
    email: str = "family@example.com",
) -> VerifiedCognitoIdentity:
    return VerifiedCognitoIdentity(
        subject=subject,
        email=email,
        email_verified=True,
        display_name="Family Member",
    )


def _invitation(
    *,
    status: str = "ISSUED",
    expires_at: datetime | None = None,
    redeemed_by_actor_id=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        elder_id=uuid4(),
        issued_by_actor_id=uuid4(),
        invitee_email_hmac=None,
        token_hash=FamilyInvitationTokenCodec(SECRET).hash_code(VALID_CODE),
        share_scope=["REPORT_DAILY", "REPORT_WEEKLY"],
        consent_id=uuid4(),
        status=status,
        expires_at=expires_at or NOW + timedelta(hours=1),
        attempt_count=0,
        max_attempts=5,
        redeemed_by_actor_id=redeemed_by_actor_id,
        redeemed_at=NOW if status == "REDEEMED" else None,
        version=2 if status == "REDEEMED" else 1,
        created_at=NOW - timedelta(minutes=10),
    )


def _service(session: _FakeSession) -> FamilyInvitationService:
    return FamilyInvitationService(session, FamilyInvitationTokenCodec(SECRET), now=lambda: NOW)


def _patch_consent(
    monkeypatch: pytest.MonkeyPatch,
    consent: object | None,
) -> AsyncMock:
    get_active = AsyncMock(return_value=consent)
    repository = MagicMock()
    repository.get_active = get_active
    monkeypatch.setattr(
        "app.services.family_invitation_service.ConsentRepository",
        lambda *_args, **_kwargs: repository,
    )
    return get_active


@pytest.mark.asyncio
async def test_create_requires_elder_role_before_database_lookup() -> None:
    session = _FakeSession()

    with pytest.raises(NotFoundError):
        await _service(session).create(
            tenant_id=uuid4(),
            elder_id=uuid4(),
            actor_id=uuid4(),
            actor_role="FAMILY_MEMBER",
            request=CreateFamilyInvitationRequest(),
            trace_id="trace-not-elder",
            idempotency_key="idem-not-elder",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_create_hides_cross_tenant_or_cross_elder_target() -> None:
    session = _FakeSession(scalar_results=[None])

    with pytest.raises(NotFoundError, match="Resource not found"):
        await _service(session).create(
            tenant_id=uuid4(),
            elder_id=uuid4(),
            actor_id=uuid4(),
            actor_role="ELDER",
            request=CreateFamilyInvitationRequest(),
            trace_id="trace-cross-scope",
            idempotency_key="idem-cross-scope",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_create_requires_active_family_sharing_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, elder_id, actor_id = uuid4(), uuid4(), uuid4()
    elder = SimpleNamespace(id=elder_id, tenant_id=tenant_id, actor_id=actor_id, status="ACTIVE")
    session = _FakeSession(scalar_results=[elder])
    _patch_consent(monkeypatch, None)

    with pytest.raises(ConflictError, match="consent must be active"):
        await _service(session).create(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role="ELDER",
            request=CreateFamilyInvitationRequest(),
            trace_id="trace-no-consent",
            idempotency_key="idem-no-consent",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_create_persists_only_code_and_email_hmac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, elder_id, actor_id = uuid4(), uuid4(), uuid4()
    elder = SimpleNamespace(id=elder_id, tenant_id=tenant_id, actor_id=actor_id, status="ACTIVE")
    consent = SimpleNamespace(
        id=uuid4(),
        version=3,
        scope={"share_scopes": ["REPORT_DAILY", "REPORT_WEEKLY", "REPORT_MONTHLY"]},
    )
    session = _FakeSession(scalar_results=[elder])
    _patch_consent(monkeypatch, consent)
    outbox = AsyncMock()
    monkeypatch.setattr("app.services.family_invitation_service.write_outbox_entry", outbox)
    service = _service(session)

    result = await service.create(
        tenant_id=tenant_id,
        elder_id=elder_id,
        actor_id=actor_id,
        actor_role="ELDER",
        request=CreateFamilyInvitationRequest(invitee_email="Family@Example.COM"),
        trace_id="trace-create",
        idempotency_key="idem-create",
    )

    invitation = next(entity for entity in session.added if isinstance(entity, FamilyInvitation))
    assert result.invitation_code != invitation.token_hash
    assert len(invitation.token_hash) == 64
    assert invitation.invitee_email_hmac == FamilyInvitationTokenCodec(SECRET).hash_email(
        "family@example.com"
    )
    assert "invitation_code" not in invitation.__dict__
    assert "invitee_email" not in invitation.__dict__
    outbox_payload = outbox.await_args.kwargs["payload"]
    assert result.invitation_code not in repr(outbox_payload)
    assert "family@example.com" not in repr(outbox_payload)


@pytest.mark.asyncio
async def test_create_rejects_scope_outside_active_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, elder_id, actor_id = uuid4(), uuid4(), uuid4()
    elder = SimpleNamespace(id=elder_id, tenant_id=tenant_id, actor_id=actor_id, status="ACTIVE")
    consent = SimpleNamespace(
        id=uuid4(),
        version=1,
        scope={"share_scopes": ["REPORT_DAILY"]},
    )
    session = _FakeSession(scalar_results=[elder])
    _patch_consent(monkeypatch, consent)

    with pytest.raises(ConflictError, match="scope exceeds"):
        await _service(session).create(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role="ELDER",
            request=CreateFamilyInvitationRequest(share_scope=["REPORT_DAILY", "REPORT_WEEKLY"]),
            trace_id="trace-scope-exceeds",
            idempotency_key="idem-scope-exceeds",
        )


@pytest.mark.asyncio
async def test_unknown_well_formed_code_fails_with_generic_error() -> None:
    session = _FakeSession(execute_results=[_Result(single=None)])

    with pytest.raises(ValidationError) as exc_info:
        await _service(session).redeem(
            identity=_identity(),
            invitation_code=VALID_CODE,
            trace_id="trace-unknown",
            idempotency_key="idem-unknown",
        )

    assert exc_info.value.details[0]["reason"] == "Invitation code is unavailable"
    assert session.added == []


@pytest.mark.asyncio
async def test_expired_invitation_fails_before_identity_is_created() -> None:
    invitation = _invitation(expires_at=NOW)
    session = _FakeSession(execute_results=[_Result(single=invitation)])

    with pytest.raises(ValidationError):
        await _service(session).redeem(
            identity=_identity(),
            invitation_code=VALID_CODE,
            trace_id="trace-expired",
            idempotency_key="idem-expired",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_redeem_rechecks_current_consent_scope_before_granting_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invitation = _invitation()
    elder = SimpleNamespace(
        id=invitation.elder_id,
        tenant_id=invitation.tenant_id,
        actor_id=invitation.issued_by_actor_id,
        status="ACTIVE",
    )
    reduced_consent = SimpleNamespace(
        id=invitation.consent_id,
        version=5,
        scope={"share_scopes": ["REPORT_DAILY"]},
    )
    session = _FakeSession(
        scalar_results=[elder],
        execute_results=[_Result(single=invitation), _Result()],
    )
    _patch_consent(monkeypatch, reduced_consent)

    with pytest.raises(ValidationError):
        await _service(session).redeem(
            identity=_identity(),
            invitation_code=VALID_CODE,
            trace_id="trace-consent-reduced",
            idempotency_key="idem-consent-reduced",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_redeem_rejects_subject_already_registered_as_elder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invitation = _invitation()
    elder = SimpleNamespace(
        id=invitation.elder_id,
        tenant_id=invitation.tenant_id,
        actor_id=invitation.issued_by_actor_id,
        status="ACTIVE",
    )
    consent = SimpleNamespace(
        id=invitation.consent_id,
        version=4,
        scope={"share_scopes": list(invitation.share_scope)},
    )
    existing_actor = SimpleNamespace(id=uuid4(), actor_type="ELDER", status="ACTIVE")
    session = _FakeSession(
        scalar_results=[elder, existing_actor],
        execute_results=[_Result(single=invitation), _Result()],
    )
    _patch_consent(monkeypatch, consent)

    with pytest.raises(ConflictError, match="another role"):
        await _service(session).redeem(
            identity=_identity(),
            invitation_code=VALID_CODE,
            trace_id="trace-role-conflict",
            idempotency_key="idem-role-conflict",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_redeemed_invitation_is_unavailable_to_another_identity() -> None:
    invitation = _invitation(status="REDEEMED", redeemed_by_actor_id=uuid4())
    session = _FakeSession(
        scalar_results=[None],
        execute_results=[_Result(single=invitation)],
    )

    with pytest.raises(ValidationError):
        await _service(session).redeem(
            identity=_identity(subject="different-family-subject"),
            invitation_code=VALID_CODE,
            trace_id="trace-other",
            idempotency_key="idem-other",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_redeem_atomically_builds_membership_and_both_relationships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invitation = _invitation()
    elder = SimpleNamespace(
        id=invitation.elder_id,
        tenant_id=invitation.tenant_id,
        actor_id=invitation.issued_by_actor_id,
        status="ACTIVE",
    )
    consent = SimpleNamespace(
        id=invitation.consent_id,
        version=4,
        scope={"share_scopes": list(invitation.share_scope)},
    )
    session = _FakeSession(
        scalar_results=[elder, None, None, None, None, None],
        execute_results=[
            _Result(single=invitation),
            _Result(),
            _Result(rows=[]),
        ],
    )
    _patch_consent(monkeypatch, consent)
    outbox = AsyncMock()
    monkeypatch.setattr("app.services.family_invitation_service.write_outbox_entry", outbox)

    result = await _service(session).redeem(
        identity=_identity(),
        invitation_code=VALID_CODE,
        trace_id="trace-redeem",
        idempotency_key="idem-redeem",
    )

    actor = next(entity for entity in session.added if isinstance(entity, Actor))
    membership = next(
        entity for entity in session.added if isinstance(entity, ActorTenantMembership)
    )
    care_relationship = next(
        entity for entity in session.added if isinstance(entity, CareRelationship)
    )
    family_relationship = next(
        entity for entity in session.added if isinstance(entity, FamilyRelationship)
    )
    assert actor.actor_type == "FAMILY_MEMBER"
    assert membership.actor_id == actor.id
    assert membership.tenant_id == invitation.tenant_id
    assert membership.role_code == "FAMILY_MEMBER"
    assert care_relationship.actor_id == actor.id
    assert care_relationship.elder_id == invitation.elder_id
    assert care_relationship.scope == ["family_report:read"]
    assert family_relationship.family_actor_id == actor.id
    assert family_relationship.elder_id == invitation.elder_id
    assert family_relationship.share_scope == invitation.share_scope
    assert family_relationship.consent_id == invitation.consent_id
    assert invitation.status == "REDEEMED"
    assert invitation.redeemed_by_actor_id == actor.id
    assert result.actor_id == actor.id
    assert result.replayed is False
    outbox.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_identity_can_replay_completed_redemption() -> None:
    actor_id = uuid4()
    invitation = _invitation(status="REDEEMED", redeemed_by_actor_id=actor_id)
    actor = SimpleNamespace(id=actor_id, cognito_sub="family-google-subject")
    relationship = SimpleNamespace(id=uuid4())
    family_relationship = SimpleNamespace(id=uuid4())
    session = _FakeSession(
        scalar_results=[actor, relationship, family_relationship],
        execute_results=[_Result(single=invitation)],
    )

    result = await _service(session).redeem(
        identity=_identity(),
        invitation_code=VALID_CODE,
        trace_id="trace-replay",
        idempotency_key="idem-replay",
    )

    assert result.actor_id == actor_id
    assert result.relationship_id == relationship.id
    assert result.family_relationship_id == family_relationship.id
    assert result.replayed is True
    assert session.added == []

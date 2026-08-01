"""Unit tests for atomic Google-backed elder onboarding."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.adapters.auth.cognito import VerifiedCognitoIdentity
from app.core.exceptions import ConflictError
from app.models.actor import Actor
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant
from app.schemas.onboarding import ElderOnboardingRequest
from app.services.onboarding_service import OnboardingService


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _Result:
    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = rows or []

    def scalars(self) -> _ScalarRows:
        return _ScalarRows(self._rows)


class _FakeSession:
    def __init__(
        self,
        *,
        scalar_results: list[object | None],
        execute_results: list[object] | None = None,
    ) -> None:
        self._scalar_results = deque(scalar_results)
        self._execute_results = deque(execute_results or [])
        self.added: list[object] = []
        self.execute_calls: list[tuple[object, object | None]] = []

    async def execute(self, statement: object, parameters: object | None = None) -> object:
        self.execute_calls.append((statement, parameters))
        return self._execute_results.popleft() if self._execute_results else _Result()

    async def scalar(self, statement: object) -> object | None:
        del statement
        return self._scalar_results.popleft()

    def add_all(self, entities: tuple[object, ...]) -> None:
        self.added.extend(entities)

    async def flush(self) -> None:
        now = datetime.now(UTC)
        for entity in self.added:
            if getattr(entity, "id", None) is None:
                entity.id = uuid4()
            if getattr(entity, "created_at", None) is None:
                entity.created_at = now
            if getattr(entity, "updated_at", None) is None:
                entity.updated_at = now


def _identity(subject: str = "google-subject-1", email: str = "elder@example.com"):
    return VerifiedCognitoIdentity(subject=subject, email=email, email_verified=True)


def _request() -> ElderOnboardingRequest:
    return ElderOnboardingRequest(display_name="林奶奶", preferred_name="阿林")


@pytest.mark.asyncio
async def test_existing_non_elder_subject_is_a_role_collision() -> None:
    actor = Actor(
        actor_type="FAMILY_MEMBER",
        cognito_sub="google-subject-1",
        display_name="Family",
        email="family@example.com",
        status="ACTIVE",
    )
    actor.id = uuid4()
    session = _FakeSession(scalar_results=[actor])

    with pytest.raises(ConflictError, match="another role"):
        await OnboardingService(session).onboard_elder(
            identity=_identity(),
            request=_request(),
            trace_id="trace-role-collision",
            idempotency_key="idem-role-collision",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_same_email_with_different_subject_requires_review() -> None:
    email_owner = Actor(
        actor_type="ELDER",
        cognito_sub="different-google-subject",
        display_name="Existing elder",
        email="elder@example.com",
        status="ACTIVE",
    )
    email_owner.id = uuid4()
    session = _FakeSession(scalar_results=[None, email_owner])

    with pytest.raises(ConflictError, match="administrator review"):
        await OnboardingService(session).onboard_elder(
            identity=_identity(email="ELDER@EXAMPLE.COM"),
            request=_request(),
            trace_id="trace-email-collision",
            idempotency_key="idem-email-collision",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_same_elder_identity_replays_existing_registration() -> None:
    actor_id, tenant_id, elder_id = uuid4(), uuid4(), uuid4()
    actor = Actor(
        actor_type="ELDER",
        cognito_sub="google-subject-1",
        display_name="林奶奶",
        email="elder@example.com",
        status="ACTIVE",
    )
    actor.id = actor_id
    elder = Elder(
        tenant_id=tenant_id,
        actor_id=actor_id,
        display_name="林奶奶",
        primary_care_setting="INDEPENDENT",
        status="ACTIVE",
    )
    elder.id = elder_id
    session = _FakeSession(
        scalar_results=[actor, 1],
        execute_results=[_Result(), _Result([elder])],
    )

    result = await OnboardingService(session).onboard_elder(
        identity=_identity(),
        request=_request(),
        trace_id="trace-replay",
        idempotency_key="idem-replay",
    )

    assert result.actor_id == actor_id
    assert result.tenant_id == tenant_id
    assert result.elder_id == elder_id
    assert result.replayed is True
    assert session.added == []
    elder_statement = session.execute_calls[1][0]
    elder_sql = str(elder_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "JOIN eldercare_ai.tenant" in elder_sql
    assert "eldercare_ai.tenant.status = 'ACTIVE'" in elder_sql
    assert "eldercare_ai.tenant.tenant_type = 'HOUSEHOLD'" in elder_sql


@pytest.mark.asyncio
async def test_new_elder_creates_one_household_actor_membership_and_elder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(scalar_results=[None, None])
    outbox = AsyncMock()
    monkeypatch.setattr("app.services.onboarding_service.write_outbox_entry", outbox)

    result = await OnboardingService(session).onboard_elder(
        identity=_identity(email="ELDER@EXAMPLE.COM"),
        request=_request(),
        trace_id="trace-new",
        idempotency_key="idem-new",
    )

    tenant = next(entity for entity in session.added if isinstance(entity, Tenant))
    actor = next(entity for entity in session.added if isinstance(entity, Actor))
    elder = next(entity for entity in session.added if isinstance(entity, Elder))
    membership = next(
        entity for entity in session.added if isinstance(entity, ActorTenantMembership)
    )
    assert tenant.tenant_type == "HOUSEHOLD"
    assert actor.actor_type == "ELDER"
    assert actor.email == "elder@example.com"
    assert elder.actor_id == actor.id
    assert elder.tenant_id == tenant.id
    assert membership.actor_id == actor.id
    assert membership.tenant_id == tenant.id
    assert membership.role_code == "ELDER"
    assert result.actor_id == actor.id
    assert result.tenant_id == tenant.id
    assert result.elder_id == elder.id
    assert result.replayed is False
    outbox.assert_awaited_once()

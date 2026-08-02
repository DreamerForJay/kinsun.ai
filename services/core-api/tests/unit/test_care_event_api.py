"""Care-event API serialization, filtering, and formal-read safety tests."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.api import care_events
from app.api.care_events import _response
from app.core.exceptions import NotFoundError, ValidationError
from app.middleware.auth import ActorContext
from app.repositories.care_event_repo import CareEventRepository
from app.schemas.care_event import CareEventType


def _actor() -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role="DAYCARE_CARE_WORKER",
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_care_event_response_filters_non_opaque_evidence_references() -> None:
    valid_reference = f"evidence:{uuid4()}"
    event = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        event_type="MEAL",
        event_time=None,
        status="NEEDS_REVIEW",
        current_version=1,
        consent_version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    version = SimpleNamespace(
        structured_payload={"meal_status": "mentioned"},
        evidence_text_ref=json.dumps(
            [
                valid_reference,
                "raw transcript must not be returned from evidence storage",
            ]
        ),
        confidence=Decimal("0.6000"),
    )
    service = SimpleNamespace(get_version=AsyncMock(return_value=version))

    response = await _response(service, event)

    assert response.evidence_refs == [valid_reference]


@pytest.mark.asyncio
async def test_list_care_events_defaults_to_formal_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(list_for_elder=AsyncMock(return_value=[]))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    await care_events.list_care_events(
        elder_id=elder_id,
        event_status=None,
        event_type=None,
        date_from=None,
        date_to=None,
        cursor=None,
        limit=50,
        actor_context=actor,
        session=session,
    )

    authorize.assert_awaited_once_with(session, actor, elder_id, "care_event:read")
    service.list_for_elder.assert_awaited_once_with(
        elder_id=elder_id,
        statuses=list(care_events.FORMAL_CARE_EVENT_STATUSES),
        event_type=None,
        event_time_from=None,
        event_time_to=None,
        limit=50,
        cursor=None,
    )


@pytest.mark.asyncio
async def test_list_care_events_requires_review_scope_for_non_formal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(list_for_elder=AsyncMock(return_value=[]))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    await care_events.list_care_events(
        elder_id=elder_id,
        event_status=["NEEDS_REVIEW"],
        event_type=None,
        date_from=None,
        date_to=None,
        cursor=None,
        limit=50,
        actor_context=actor,
        session=session,
    )

    assert authorize.await_args_list == [
        call(session, actor, elder_id, "care_event:read"),
        call(session, actor, elder_id, "care_event:review"),
    ]
    service.list_for_elder.assert_awaited_once_with(
        elder_id=elder_id,
        statuses=["NEEDS_REVIEW"],
        event_type=None,
        event_time_from=None,
        event_time_to=None,
        limit=50,
        cursor=None,
    )


@pytest.mark.asyncio
async def test_list_care_events_forwards_type_and_inclusive_utc_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    actor = _actor()
    session = MagicMock()
    service = SimpleNamespace(list_for_elder=AsyncMock(return_value=[]))
    monkeypatch.setattr(care_events, "authorize_elder", AsyncMock())
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    await care_events.list_care_events(
        elder_id=elder_id,
        event_status=None,
        event_type=CareEventType.MEAL,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 2),
        cursor=None,
        limit=25,
        actor_context=actor,
        session=session,
    )

    service.list_for_elder.assert_awaited_once_with(
        elder_id=elder_id,
        statuses=list(care_events.FORMAL_CARE_EVENT_STATUSES),
        event_type="MEAL",
        event_time_from=datetime(2026, 8, 1, tzinfo=UTC),
        event_time_to=datetime.combine(date(2026, 8, 2), time.max, tzinfo=UTC),
        limit=25,
        cursor=None,
    )


@pytest.mark.asyncio
async def test_list_care_events_rejects_reversed_date_range_after_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service_factory = MagicMock()
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", service_factory)

    with pytest.raises(ValidationError) as exc_info:
        await care_events.list_care_events(
            elder_id=elder_id,
            event_status=None,
            event_type=None,
            date_from=date(2026, 8, 3),
            date_to=date(2026, 8, 2),
            cursor=None,
            limit=50,
            actor_context=actor,
            session=session,
        )

    authorize.assert_awaited_once_with(session, actor, elder_id, "care_event:read")
    assert exc_info.value.details == [
        {
            "field": "date_from",
            "reason": "date_from must be on or before date_to",
        }
    ]
    service_factory.assert_not_called()


@pytest.mark.asyncio
async def test_repository_applies_tenant_elder_type_and_time_filters() -> None:
    tenant_id = uuid4()
    elder_id = uuid4()
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    repository = CareEventRepository(session, tenant_id)
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime.combine(date(2026, 8, 2), time.max, tzinfo=UTC)

    await repository.list_for_elder(
        elder_id=elder_id,
        statuses=["VERIFIED"],
        event_type="MEAL",
        event_time_from=start,
        event_time_to=end,
        limit=20,
        cursor=None,
    )

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(compile_kwargs={"literal_binds": False})
    sql = str(compiled)
    values = tuple(compiled.params.values())
    assert "care_event.tenant_id =" in sql
    assert "care_event.elder_id =" in sql
    assert "care_event.event_type =" in sql
    assert "coalesce(" in sql
    assert " >= " in sql
    assert " <= " in sql
    assert tenant_id in values
    assert elder_id in values
    assert "MEAL" in values
    assert start in values
    assert end in values


@pytest.mark.asyncio
async def test_get_care_event_does_not_read_non_formal_event_before_review_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    event_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock(
        side_effect=[None, NotFoundError("Resource not found")],
    )
    service = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    with pytest.raises(NotFoundError):
        await care_events.get_care_event(
            elder_id=elder_id,
            event_id=event_id,
            actor_context=actor,
            session=session,
        )

    assert authorize.await_args_list == [
        call(session, actor, elder_id, "care_event:read"),
        call(session, actor, elder_id, "care_event:review"),
    ]
    service.get.assert_awaited_once_with(
        elder_id,
        event_id,
        statuses=list(care_events.FORMAL_CARE_EVENT_STATUSES),
    )


@pytest.mark.asyncio
async def test_get_care_event_reviewer_fallback_excludes_deleted_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    event_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(get=AsyncMock(side_effect=[None, None]))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    with pytest.raises(NotFoundError):
        await care_events.get_care_event(
            elder_id=elder_id,
            event_id=event_id,
            actor_context=actor,
            session=session,
        )

    assert service.get.await_args_list == [
        call(
            elder_id,
            event_id,
            statuses=list(care_events.FORMAL_CARE_EVENT_STATUSES),
        ),
        call(
            elder_id,
            event_id,
            statuses=list(care_events.REVIEWABLE_CARE_EVENT_STATUSES),
        ),
    ]
    assert "DELETED" not in care_events.REVIEWABLE_CARE_EVENT_STATUSES

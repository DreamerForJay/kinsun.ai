"""PostgreSQL-backed Voice Ticket issue, consume, and revocation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.actor import Actor
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.outbox import OutboxEvent
from app.models.policy import PolicyRegistry
from app.models.tenant import Tenant
from app.services.voice_ticket_codec import VoiceTicketCodec, get_voice_ticket_codec
from tests.integration import test_identity_api as identity_api_tests

SECRET = "integration-voice-ticket-secret-material-32-bytes"


@pytest.fixture
def voice_ids() -> dict[str, UUID]:
    return {
        "tenant_id": uuid4(),
        "tenant_b_id": uuid4(),
        "actor_id": uuid4(),
        "elder_id": uuid4(),
        "elder_b_id": uuid4(),
        "system_actor_id": uuid4(),
        "policy_id": uuid4(),
        "consent_id": uuid4(),
    }


@pytest_asyncio.fixture
async def voice_data(committed_session, voice_ids):
    ids = voice_ids
    now = datetime.now(UTC)
    committed_session.add_all(
        [
            Tenant(
                id=ids["tenant_id"],
                name="Synthetic Voice Household",
                tenant_type="HOUSEHOLD",
            ),
            Tenant(
                id=ids["tenant_b_id"],
                name="Synthetic Other Household",
                tenant_type="HOUSEHOLD",
            ),
            Actor(
                id=ids["actor_id"],
                actor_type="ELDER",
                display_name="Synthetic Voice Elder",
            ),
        ]
    )
    await committed_session.flush()
    committed_session.add_all(
        [
            Elder(
                id=ids["elder_id"],
                actor_id=ids["actor_id"],
                tenant_id=ids["tenant_id"],
                display_name="Synthetic Voice Elder",
                primary_care_setting="HOME_CARE",
            ),
            Elder(
                id=ids["elder_b_id"],
                tenant_id=ids["tenant_b_id"],
                display_name="Synthetic Other Elder",
                primary_care_setting="HOME_CARE",
            ),
            PolicyRegistry(
                id=ids["policy_id"],
                owner_tenant_id=ids["tenant_id"],
                policy_code=f"voice-ticket-integration-{ids['policy_id']}",
                policy_type="CONSENT",
                version="voice-ticket-v1",
                status="ACTIVE",
                policy_payload={"synthetic": True},
                effective_from=now - timedelta(days=1),
                approved_by_actor_id=ids["actor_id"],
            ),
        ]
    )
    await committed_session.flush()
    committed_session.add(
        ConsentGrant(
            id=ids["consent_id"],
            elder_id=ids["elder_id"],
            purpose_code="BASIC_VOICE",
            status="GRANTED",
            version=1,
            scope={},
            granted_by_actor_id=ids["actor_id"],
            policy_id=ids["policy_id"],
            granted_at=now,
            effective_at=now - timedelta(minutes=1),
        )
    )
    await committed_session.commit()
    yield ids


def _app(test_engine, ids, *, role: str, tenant_key: str = "tenant_id", codec):
    actor_id = ids["actor_id"] if role == "ELDER" else ids["system_actor_id"]
    app = identity_api_tests._build_client_app(
        test_engine,
        actor_id=actor_id,
        actor_role=role,
        tenant_id=ids[tenant_key],
    )
    app.dependency_overrides[get_voice_ticket_codec] = lambda: codec
    return app


async def _counts(test_engine) -> tuple[int, int]:
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        sessions = await session.scalar(select(func.count()).select_from(ConversationSession))
        outbox = await session.scalar(select(func.count()).select_from(OutboxEvent))
        return sessions or 0, outbox or 0


async def _issue(client: AsyncClient, elder_id: UUID, key: str = "voice-ticket-issue-1"):
    return await client.post(
        f"/api/v1/elders/{elder_id}/voice-tickets",
        headers={"Idempotency-Key": key},
        json={
            "language_preference": "ZH_TW",
            "input_mode": "voice_with_text_fallback",
            "client_audio_format": "audio/webm",
            "client_timezone": "Asia/Taipei",
            "purpose": "BASIC_VOICE",
        },
    )


@pytest.mark.asyncio
async def test_ticket_issue_is_idempotent_and_consume_is_single_use(
    test_engine,
    voice_data,
) -> None:
    ids = voice_data
    codec = VoiceTicketCodec(SECRET)
    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        issued = await _issue(client, ids["elder_id"])
        replayed_issue = await _issue(client, ids["elder_id"])

    assert issued.status_code == 201
    assert replayed_issue.status_code == 201
    ticket_data = issued.json()["data"]
    assert replayed_issue.json()["data"]["voice_ticket"] == ticket_data["voice_ticket"]
    assert ticket_data["voice_session"]["state"] == "CREATED"
    assert str(ids["actor_id"]) not in ticket_data["voice_ticket"]
    assert str(ids["tenant_id"]) not in ticket_data["voice_ticket"]

    system_app = _app(test_engine, ids, role="SYSTEM_SERVICE", codec=codec)
    payload = {
        "session_id": ticket_data["voice_session"]["session_id"],
        "voice_ticket": ticket_data["voice_ticket"],
    }
    async with AsyncClient(
        transport=ASGITransport(app=system_app),
        base_url="http://test",
    ) as client:
        consumed = await client.post("/api/v1/internal/voice-tickets/consume", json=payload)
        replayed_consume = await client.post(
            "/api/v1/internal/voice-tickets/consume",
            json=payload,
        )

    assert consumed.status_code == 200
    assert consumed.json()["data"]["state"] == "RECORDING"
    assert replayed_consume.status_code == 401
    assert ticket_data["voice_ticket"] not in replayed_consume.text


@pytest.mark.asyncio
async def test_revocation_cancels_active_session_and_invalidates_ticket(
    test_engine,
    voice_data,
) -> None:
    ids = voice_data
    codec = VoiceTicketCodec(SECRET)
    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        issued = await _issue(client, ids["elder_id"], "voice-ticket-before-revoke")
    data = issued.json()["data"]

    system_app = _app(test_engine, ids, role="SYSTEM_SERVICE", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=system_app),
        base_url="http://test",
    ) as client:
        consumed = await client.post(
            "/api/v1/internal/voice-tickets/consume",
            json={
                "session_id": data["voice_session"]["session_id"],
                "voice_ticket": data["voice_ticket"],
            },
        )
    assert consumed.status_code == 200

    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        revoked = await client.post(
            f"/api/v1/elders/{ids['elder_id']}/consents/{ids['consent_id']}/revoke",
            headers={"Idempotency-Key": "revoke-basic-voice-1"},
            json={
                "reason_code": "ELDER_REQUEST",
                "request_deletion": False,
                "revoke_scope": [],
            },
        )
    assert revoked.status_code == 200

    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        current = await client.get(
            f"/api/v1/voice-sessions/{data['voice_session']['session_id']}"
        )
    assert current.status_code == 200
    assert current.json()["data"]["state"] == "CANCELLED"
    assert current.json()["data"]["ended_at"] is not None


@pytest.mark.asyncio
async def test_unconsumed_ticket_is_invalid_after_revocation(
    test_engine,
    voice_data,
) -> None:
    ids = voice_data
    codec = VoiceTicketCodec(SECRET)
    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        issued = await _issue(client, ids["elder_id"], "voice-ticket-unconsumed")
        data = issued.json()["data"]
        revoked = await client.post(
            f"/api/v1/elders/{ids['elder_id']}/consents/{ids['consent_id']}/revoke",
            headers={"Idempotency-Key": "revoke-basic-voice-2"},
            json={
                "reason_code": "ELDER_STOPPED",
                "request_deletion": False,
                "revoke_scope": [],
            },
        )
    assert revoked.status_code == 200

    system_app = _app(test_engine, ids, role="SYSTEM_SERVICE", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=system_app),
        base_url="http://test",
    ) as client:
        consumed = await client.post(
            "/api/v1/internal/voice-tickets/consume",
            json={
                "session_id": data["voice_session"]["session_id"],
                "voice_ticket": data["voice_ticket"],
            },
        )
    assert consumed.status_code == 401
    assert data["voice_ticket"] not in consumed.text


@pytest.mark.asyncio
async def test_expired_and_cross_tenant_ticket_fail_without_sensitive_echo(
    test_engine,
    voice_data,
) -> None:
    ids = voice_data
    clock = [datetime.now(UTC)]
    codec = VoiceTicketCodec(SECRET, now=lambda: clock[0])
    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        issued = await _issue(client, ids["elder_id"], "voice-ticket-expiry")
    data = issued.json()["data"]
    clock[0] = datetime.fromisoformat(data["expires_at"])

    payload = {
        "session_id": data["voice_session"]["session_id"],
        "voice_ticket": data["voice_ticket"],
    }
    expired_app = _app(test_engine, ids, role="SYSTEM_SERVICE", codec=codec)
    cross_tenant_app = _app(
        test_engine,
        ids,
        role="SYSTEM_SERVICE",
        tenant_key="tenant_b_id",
        codec=codec,
    )
    async with AsyncClient(
        transport=ASGITransport(app=expired_app),
        base_url="http://test",
    ) as client:
        expired = await client.post("/api/v1/internal/voice-tickets/consume", json=payload)
    async with AsyncClient(
        transport=ASGITransport(app=cross_tenant_app),
        base_url="http://test",
    ) as client:
        cross_tenant = await client.post(
            "/api/v1/internal/voice-tickets/consume",
            json=payload,
        )

    assert expired.status_code == cross_tenant.status_code == 401
    assert expired.json()["error"]["reason_code"] == "AUTHENTICATION_FAILED"
    assert cross_tenant.json()["error"]["reason_code"] == "AUTHENTICATION_FAILED"
    assert data["voice_ticket"] not in expired.text + cross_tenant.text


@pytest.mark.asyncio
async def test_cross_tenant_issue_has_zero_session_or_outbox_side_effect(
    test_engine,
    voice_data,
) -> None:
    ids = voice_data
    codec = VoiceTicketCodec(SECRET)
    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    before = await _counts(test_engine)

    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        denied = await _issue(client, ids["elder_b_id"], "voice-ticket-cross-tenant")
    assert denied.status_code == 404

    after = await _counts(test_engine)
    assert after == before

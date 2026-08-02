"""PostgreSQL-backed Voice Ticket issue, consume, and revocation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.actor import Actor
from app.models.asr_gate import AsrGateEvidence
from app.models.care_assignment import CareAssignment
from app.models.care_unit import CareUnit
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.outbox import OutboxEvent
from app.models.policy import PolicyRegistry
from app.models.tenant import Tenant
from app.services.voice_ticket_codec import VoiceTicketCodec, get_voice_ticket_codec
from tests.integration import test_identity_api as identity_api_tests

SECRET = "integration-voice-ticket-secret-material-32-bytes"


@pytest.fixture(autouse=True)
def enable_asr_gate(monkeypatch):
    monkeypatch.setenv("ASR_GATE_ENABLED", "true")
    monkeypatch.setenv("ASR_GATE_HMAC_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def voice_ids() -> dict[str, UUID]:
    return {
        "tenant_id": uuid4(),
        "tenant_b_id": uuid4(),
        "actor_id": uuid4(),
        "no_consent_actor_id": uuid4(),
        "worker_id": uuid4(),
        "elder_id": uuid4(),
        "elder_b_id": uuid4(),
        "elder_no_consent_id": uuid4(),
        "system_actor_id": uuid4(),
        "care_unit_id": uuid4(),
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
            Actor(
                id=ids["no_consent_actor_id"],
                actor_type="ELDER",
                display_name="Synthetic Elder Without Consent",
            ),
            Actor(
                id=ids["worker_id"],
                actor_type="HOME_CARE_WORKER",
                display_name="Synthetic Expired Worker",
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
            Elder(
                id=ids["elder_no_consent_id"],
                actor_id=ids["no_consent_actor_id"],
                tenant_id=ids["tenant_id"],
                display_name="Synthetic Elder Without Consent",
                primary_care_setting="HOME_CARE",
            ),
            CareUnit(
                id=ids["care_unit_id"],
                tenant_id=ids["tenant_id"],
                unit_type="HOME_CARE_AGENCY",
                name="Synthetic Expired Assignment Agency",
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
    committed_session.add_all(
        [
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
            ),
            CareAssignment(
                care_unit_id=ids["care_unit_id"],
                elder_id=ids["elder_id"],
                worker_id=ids["worker_id"],
                tenant_id=ids["tenant_id"],
                service_start=now - timedelta(hours=2),
                service_end=now - timedelta(hours=1),
                service_scope=["voice_session:create"],
                status="CONFIRMED",
            ),
        ]
    )
    await committed_session.commit()
    yield ids


def _app(
    test_engine,
    ids,
    *,
    role: str,
    tenant_key: str = "tenant_id",
    actor_key: str | None = None,
    codec,
):
    if actor_key is not None:
        actor_id = ids[actor_key]
    else:
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
        current = await client.get(f"/api/v1/voice-sessions/{data['voice_session']['session_id']}")
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

    before_reissue = await _counts(test_engine)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        denied_reissue = await _issue(
            client,
            ids["elder_id"],
            "voice-ticket-after-revoke",
        )
    assert denied_reissue.status_code == 404
    assert await _counts(test_engine) == before_reissue

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


@pytest.mark.asyncio
async def test_missing_consent_and_same_tenant_cross_elder_issue_are_denied(
    test_engine,
    voice_data,
) -> None:
    ids = voice_data
    codec = VoiceTicketCodec(SECRET)
    before = await _counts(test_engine)

    no_consent_app = _app(
        test_engine,
        ids,
        role="ELDER",
        actor_key="no_consent_actor_id",
        codec=codec,
    )
    async with AsyncClient(
        transport=ASGITransport(app=no_consent_app),
        base_url="http://test",
    ) as client:
        missing_consent = await _issue(
            client,
            ids["elder_no_consent_id"],
            "voice-ticket-missing-consent",
        )

    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app),
        base_url="http://test",
    ) as client:
        cross_elder = await _issue(
            client,
            ids["elder_no_consent_id"],
            "voice-ticket-same-tenant-cross-elder",
        )

    assert missing_consent.status_code == cross_elder.status_code == 404
    assert (
        missing_consent.json()["error"]["reason_code"]
        == cross_elder.json()["error"]["reason_code"]
        == "RESOURCE_NOT_FOUND"
    )
    assert await _counts(test_engine) == before


@pytest.mark.asyncio
async def test_expired_assignment_issue_has_zero_session_or_outbox_side_effect(
    test_engine,
    voice_data,
) -> None:
    ids = voice_data
    codec = VoiceTicketCodec(SECRET)
    worker_app = _app(
        test_engine,
        ids,
        role="HOME_CARE_WORKER",
        actor_key="worker_id",
        codec=codec,
    )
    before = await _counts(test_engine)

    async with AsyncClient(
        transport=ASGITransport(app=worker_app),
        base_url="http://test",
    ) as client:
        denied = await _issue(
            client,
            ids["elder_id"],
            "voice-ticket-expired-assignment",
        )

    assert denied.status_code == 404
    assert denied.json()["error"]["reason_code"] == "RESOURCE_NOT_FOUND"
    assert await _counts(test_engine) == before


async def _consume_for_asr(test_engine, ids, codec, key: str) -> dict:
    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app), base_url="http://test"
    ) as client:
        issued = await _issue(client, ids["elder_id"], key)
    data = issued.json()["data"]
    system_app = _app(test_engine, ids, role="SYSTEM_SERVICE", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=system_app), base_url="http://test"
    ) as client:
        consumed = await client.post(
            "/api/v1/internal/voice-tickets/consume",
            json={
                "session_id": data["voice_session"]["session_id"],
                "voice_ticket": data["voice_ticket"],
            },
        )
    assert consumed.status_code == 200
    return data


async def _submit_asr(app, payload: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/v1/internal/asr-results", json=payload)


@pytest.mark.asyncio
async def test_low_confidence_requires_elder_confirmation_and_never_returns_restricted_data(
    test_engine, voice_data
) -> None:
    ids = voice_data
    codec = VoiceTicketCodec(SECRET)
    ticket = await _consume_for_asr(test_engine, ids, codec, "asr-low")
    system_app = _app(test_engine, ids, role="SYSTEM_SERVICE", codec=codec)
    transcript = "synthetic low-confidence utterance"
    payload = {
        "session_id": ticket["voice_session"]["session_id"],
        "language_route": "ZH_TW",
        "asr_model_version": "synthetic-asr-v1",
        "confidence": 0.42,
        "transcript": transcript,
    }
    submitted = await _submit_asr(system_app, payload)
    replayed = await _submit_asr(system_app, payload)
    assert submitted.status_code == replayed.status_code == 200
    assert submitted.json()["data"]["decision"] == "CONFIRMATION_REQUIRED"
    assert transcript not in submitted.text
    assert "confidence" not in submitted.json()["data"]

    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        evidence = await session.scalar(select(AsrGateEvidence))
        conversation = await session.get(ConversationSession, UUID(payload["session_id"]))
        assert evidence is not None
        assert evidence.transcript is None
        assert evidence.transcript_digest != transcript
        assert conversation is not None and conversation.state == "AWAITING_CONFIRMATION"

    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app), base_url="http://test"
    ) as client:
        confirmed = await client.post(
            f"/api/v1/voice-sessions/{payload['session_id']}/asr-confirmation",
            headers={"Idempotency-Key": "asr-confirm-1"},
            json={"action": "CONFIRM"},
        )
        confirmed_replay = await client.post(
            f"/api/v1/voice-sessions/{payload['session_id']}/asr-confirmation",
            headers={"Idempotency-Key": "asr-confirm-1"},
            json={"action": "CONFIRM"},
        )
    assert confirmed.status_code == confirmed_replay.status_code == 200
    assert confirmed.json()["data"]["decision"] == "CAN_SEND_TO_AGENT"


@pytest.mark.asyncio
async def test_asr_gate_rejects_wrong_language_wrong_elder_and_revoked_consent(
    test_engine, voice_data
) -> None:
    ids = voice_data
    codec = VoiceTicketCodec(SECRET)
    ticket = await _consume_for_asr(test_engine, ids, codec, "asr-negative")
    system_app = _app(test_engine, ids, role="SYSTEM_SERVICE", codec=codec)
    payload = {
        "session_id": ticket["voice_session"]["session_id"],
        "language_route": "NAN_TW",
        "asr_model_version": "synthetic-asr-v1",
        "confidence": 0.99,
        "transcript": "synthetic wrong language",
    }
    wrong_language = await _submit_asr(system_app, payload)
    assert wrong_language.status_code == 401

    payload["language_route"] = "ZH_TW"
    cross_tenant_app = _app(
        test_engine,
        ids,
        role="SYSTEM_SERVICE",
        tenant_key="tenant_b_id",
        codec=codec,
    )
    cross_tenant = await _submit_asr(cross_tenant_app, payload)
    assert cross_tenant.status_code == 401

    payload["confidence"] = 0.1
    low = await _submit_asr(system_app, payload)
    assert low.status_code == 200
    wrong_elder_app = _app(
        test_engine,
        ids,
        role="ELDER",
        actor_key="no_consent_actor_id",
        codec=codec,
    )
    async with AsyncClient(
        transport=ASGITransport(app=wrong_elder_app), base_url="http://test"
    ) as client:
        wrong_elder = await client.post(
            f"/api/v1/voice-sessions/{payload['session_id']}/asr-confirmation",
            headers={"Idempotency-Key": "asr-wrong-elder"},
            json={"action": "CONFIRM"},
        )
    assert wrong_elder.status_code == 404

    elder_app = _app(test_engine, ids, role="ELDER", codec=codec)
    async with AsyncClient(
        transport=ASGITransport(app=elder_app), base_url="http://test"
    ) as client:
        revoked = await client.post(
            f"/api/v1/elders/{ids['elder_id']}/consents/{ids['consent_id']}/revoke",
            headers={"Idempotency-Key": "asr-revoke"},
            json={"reason_code": "ELDER_REQUEST", "request_deletion": False, "revoke_scope": []},
        )
        after_revoke = await client.post(
            f"/api/v1/voice-sessions/{payload['session_id']}/asr-confirmation",
            headers={"Idempotency-Key": "asr-after-revoke"},
            json={"action": "CONFIRM"},
        )
    assert revoked.status_code == 200
    assert after_revoke.status_code == 401

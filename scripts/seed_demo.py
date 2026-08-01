"""Insert deterministic, synthetic-only Demo personas into an empty local database."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_API_ROOT = REPO_ROOT / "services" / "core-api"
sys.path.insert(0, str(CORE_API_ROOT))

from app.models.actor import Actor  # noqa: E402
from app.models.care_assignment import CareAssignment  # noqa: E402
from app.models.care_event import CareEvent, CareEventVersion  # noqa: E402
from app.models.care_relationship import CareRelationship  # noqa: E402
from app.models.care_unit import CareUnit  # noqa: E402
from app.models.consent import ConsentGrant  # noqa: E402
from app.models.elder import Elder  # noqa: E402
from app.models.membership import ActorTenantMembership  # noqa: E402
from app.models.memory import Memory, MemoryVersion  # noqa: E402
from app.models.outbox import OutboxEvent  # noqa: E402
from app.models.policy import PolicyRegistry  # noqa: E402
from app.models.report import FamilyRelationship, FamilyReport, ReportVersion  # noqa: E402
from app.models.summary import DailySummary, SummaryVersion  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402

EXPECTED_REVISION = "c1a9e7f24b63"
MANIFEST_PATH = REPO_ROOT / "data" / "seed" / "demo_ids.json"
ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
E2E_DATABASE_PREFIX = "kinsun_frontend_e2e_"


def _load_repo_env() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _database_url() -> str:
    _load_repo_env()
    if os.getenv("APP_ENV", "development").lower() != "development":
        raise RuntimeError("Demo seed is allowed only when APP_ENV=development")
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    parsed = urlparse(value)
    if parsed.scheme != "postgresql+asyncpg":
        raise RuntimeError("DATABASE_URL must use postgresql+asyncpg")
    database_name = parsed.path.removeprefix("/")
    allow_e2e = os.getenv("KINSUN_ALLOW_SYNTHETIC_E2E_SEED", "false").lower() == "true"
    allowed_database = database_name == "kinsun" or (
        allow_e2e and database_name.startswith(E2E_DATABASE_PREFIX)
    )
    if parsed.hostname not in ALLOWED_LOCAL_HOSTS or not allowed_database:
        raise RuntimeError(
            "Demo seed is restricted to local kinsun; synthetic E2E databases require "
            "KINSUN_ALLOW_SYNTHETIC_E2E_SEED=true and the kinsun_frontend_e2e_ prefix"
        )
    return value


def _id(value: str) -> UUID:
    return UUID(value)


async def _assert_empty_and_current(session: AsyncSession, daycare_tenant_id: UUID) -> None:
    revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
    if revision != EXPECTED_REVISION:
        raise RuntimeError(
            f"Database revision is {revision!r}; expected {EXPECTED_REVISION}. "
            "Run scripts/reset_demo.ps1."
        )
    exists = await session.scalar(select(Tenant.id).where(Tenant.id == daycare_tenant_id))
    if exists is not None:
        raise RuntimeError(
            "Deterministic Demo rows already exist. "
            "Use scripts/reset_demo.ps1 to rebuild instead of editing rows manually."
        )


async def _seed(session: AsyncSession, manifest: dict) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    today = date.today()

    daycare_tenant_id = _id(manifest["tenants"]["daycare"])
    home_tenant_id = _id(manifest["tenants"]["home_care"])
    actor_ids = {key: _id(value) for key, value in manifest["actors"].items()}
    unit_ids = {key: _id(value) for key, value in manifest["care_units"].items()}
    elder_ids = {key: _id(value) for key, value in manifest["elders"].items()}

    await _assert_empty_and_current(session, daycare_tenant_id)

    tenants = [
        Tenant(
            id=daycare_tenant_id,
            tenant_type="DEMO",
            name="幸福日照中心 Demo Tenant",
            status="ACTIVE",
            timezone="Asia/Taipei",
        ),
        Tenant(
            id=home_tenant_id,
            tenant_type="DEMO",
            name="安心居家服務 Demo Tenant",
            status="ACTIVE",
            timezone="Asia/Taipei",
        ),
    ]
    actors = [
        Actor(id=actor_ids["lin_elder"], actor_type="ELDER", display_name="林阿嬤"),
        Actor(id=actor_ids["zhang_elder"], actor_type="ELDER", display_name="張阿姨"),
        Actor(id=actor_ids["chen_elder"], actor_type="ELDER", display_name="陳伯伯"),
        Actor(
            id=actor_ids["daycare_worker"],
            actor_type="DAYCARE_CARE_WORKER",
            display_name="幸福日照照服員",
        ),
        Actor(
            id=actor_ids["home_worker"],
            actor_type="HOME_CARE_WORKER",
            display_name="安心居服員",
        ),
        Actor(
            id=actor_ids["chen_family"],
            actor_type="FAMILY_MEMBER",
            display_name="陳家屬",
        ),
        Actor(
            id=actor_ids["assignment_service"],
            actor_type="SYSTEM_SERVICE",
            display_name="Demo Assignment Service",
        ),
    ]
    session.add_all([*tenants, *actors])
    await session.flush()

    units = [
        CareUnit(
            id=unit_ids["幸福日照中心"],
            tenant_id=daycare_tenant_id,
            unit_type="DAYCARE_CENTER",
            name="幸福日照中心",
            status="ACTIVE",
            timezone="Asia/Taipei",
        ),
        CareUnit(
            id=unit_ids["安心居家服務"],
            tenant_id=home_tenant_id,
            unit_type="HOME_CARE_AGENCY",
            name="安心居家服務",
            status="ACTIVE",
            timezone="Asia/Taipei",
        ),
    ]
    session.add_all(units)
    await session.flush()

    elders = [
        Elder(
            id=elder_ids["林阿嬤"],
            actor_id=actor_ids["lin_elder"],
            tenant_id=daycare_tenant_id,
            primary_care_unit_id=unit_ids["幸福日照中心"],
            display_name="林阿嬤",
            preferred_name="阿嬤",
            primary_care_setting="DAYCARE",
            preferred_language="MIXED",
            response_length_preference="SHORT",
            timezone="Asia/Taipei",
        ),
        Elder(
            id=elder_ids["張阿姨"],
            actor_id=actor_ids["zhang_elder"],
            tenant_id=daycare_tenant_id,
            primary_care_unit_id=unit_ids["幸福日照中心"],
            display_name="張阿姨",
            preferred_name="張阿姨",
            primary_care_setting="DAYCARE",
            preferred_language="ZH_TW",
            response_length_preference="STANDARD",
            timezone="Asia/Taipei",
        ),
        Elder(
            id=elder_ids["陳伯伯"],
            actor_id=actor_ids["chen_elder"],
            tenant_id=home_tenant_id,
            primary_care_unit_id=unit_ids["安心居家服務"],
            display_name="陳伯伯",
            preferred_name="陳伯伯",
            primary_care_setting="HOME_CARE",
            preferred_language="ZH_TW",
            response_length_preference="SHORT",
            timezone="Asia/Taipei",
        ),
    ]
    session.add_all(elders)
    await session.flush()

    membership_rows = [
        ("50000000-0000-4000-8000-000000000001", "lin_elder", daycare_tenant_id, None),
        ("50000000-0000-4000-8000-000000000002", "zhang_elder", daycare_tenant_id, None),
        ("50000000-0000-4000-8000-000000000003", "chen_elder", home_tenant_id, None),
        ("50000000-0000-4000-8000-000000000010", "daycare_worker", daycare_tenant_id, None),
        (
            "50000000-0000-4000-8000-000000000011",
            "daycare_worker",
            daycare_tenant_id,
            unit_ids["幸福日照中心"],
        ),
        ("50000000-0000-4000-8000-000000000012", "home_worker", home_tenant_id, None),
        ("50000000-0000-4000-8000-000000000013", "chen_family", home_tenant_id, None),
        (
            "50000000-0000-4000-8000-000000000014",
            "assignment_service",
            home_tenant_id,
            None,
        ),
    ]
    session.add_all(
        [
            ActorTenantMembership(
                id=_id(row_id),
                actor_id=actor_ids[actor_key],
                tenant_id=tenant_id,
                care_unit_id=care_unit_id,
                role_code=actor_key.upper(),
                status="ACTIVE",
                effective_from=now - timedelta(days=30),
            )
            for row_id, actor_key, tenant_id, care_unit_id in membership_rows
        ]
    )

    all_core_scopes = [
        "elder:basic:read",
        "elder:access_context:read",
        "consent:read",
        "consent:write",
        "consent:revoke",
        "voice_session:create",
        "voice_session:read",
        "voice_session:control",
        "care_event:candidate:create",
        "care_event:read",
        "care_event:review",
        "memory:candidate:create",
        "memory:candidate:read",
        "memory:confirm",
        "memory:reject",
        "memory:defer",
        "memory:read",
        "memory:update",
        "memory:delete",
        "summary:draft:create",
        "summary:read",
        "summary:review",
        "summary:rebuild",
        "family_report:draft:create",
        "family_report:publish",
        "family_report:withdraw",
        "family_report:read",
        "deletion:read",
    ]
    relationships = [
        CareRelationship(
            id=_id("60000000-0000-4000-8000-000000000001"),
            elder_id=elder_ids["林阿嬤"],
            actor_id=actor_ids["daycare_worker"],
            tenant_id=daycare_tenant_id,
            care_unit_id=unit_ids["幸福日照中心"],
            relationship_type="DAYCARE_ASSIGNMENT",
            scope=all_core_scopes,
            status="ACTIVE",
            effective_from=now - timedelta(days=30),
        ),
        CareRelationship(
            id=_id("60000000-0000-4000-8000-000000000002"),
            elder_id=elder_ids["張阿姨"],
            actor_id=actor_ids["daycare_worker"],
            tenant_id=daycare_tenant_id,
            care_unit_id=unit_ids["幸福日照中心"],
            relationship_type="DAYCARE_ASSIGNMENT",
            scope=all_core_scopes,
            status="ACTIVE",
            effective_from=now - timedelta(days=30),
        ),
        CareRelationship(
            id=_id("60000000-0000-4000-8000-000000000003"),
            elder_id=elder_ids["陳伯伯"],
            actor_id=actor_ids["chen_family"],
            tenant_id=home_tenant_id,
            relationship_type="FAMILY_SHARE",
            scope=["elder:basic:read", "family_report:read"],
            status="ACTIVE",
            effective_from=now - timedelta(days=30),
        ),
        CareRelationship(
            id=_id("60000000-0000-4000-8000-000000000004"),
            elder_id=elder_ids["陳伯伯"],
            actor_id=actor_ids["assignment_service"],
            tenant_id=home_tenant_id,
            care_unit_id=unit_ids["安心居家服務"],
            relationship_type="HOME_CARE_ASSIGNMENT",
            scope=["assignment:create", "assignment:confirm", "assignment:read"],
            status="ACTIVE",
            effective_from=now - timedelta(days=30),
        ),
    ]
    session.add_all(relationships)

    policy_id = _id("80000000-0000-4000-8000-000000000001")
    policy = PolicyRegistry(
        id=policy_id,
        owner_tenant_id=None,
        policy_code="demo-consent-policy",
        policy_type="CONSENT",
        version="demo-consent-v1",
        status="ACTIVE",
        policy_payload={"synthetic_only": True, "purpose_specific": True},
        effective_from=now - timedelta(days=30),
        approved_by_actor_id=actor_ids["assignment_service"],
    )
    session.add(policy)
    await session.flush()

    consent_ids = {key: _id(value) for key, value in manifest["consents"].items()}
    active_consent_specs = [
        ("林阿嬤_BASIC_VOICE", "林阿嬤", "BASIC_VOICE", "lin_elder"),
        (
            "林阿嬤_CARE_EVENT_EXTRACTION",
            "林阿嬤",
            "CARE_EVENT_EXTRACTION",
            "lin_elder",
        ),
        ("林阿嬤_LONG_TERM_MEMORY", "林阿嬤", "LONG_TERM_MEMORY", "lin_elder"),
        ("陳伯伯_FAMILY_SHARING", "陳伯伯", "FAMILY_SHARING", "chen_elder"),
        (
            "陳伯伯_CARE_EVENT_EXTRACTION",
            "陳伯伯",
            "CARE_EVENT_EXTRACTION",
            "chen_elder",
        ),
    ]
    session.add_all(
        [
            ConsentGrant(
                id=consent_ids[key],
                elder_id=elder_ids[elder_key],
                purpose_code=purpose,
                status="GRANTED",
                version=1,
                scope={"share_scopes": ["REPORT"] if purpose == "FAMILY_SHARING" else []},
                granted_by_actor_id=actor_ids[actor_key],
                policy_id=policy_id,
                granted_at=now - timedelta(days=7),
                effective_at=now - timedelta(days=7),
            )
            for key, elder_key, purpose, actor_key in active_consent_specs
        ]
    )
    session.add(
        ConsentGrant(
            id=consent_ids["張阿姨_PROACTIVE_COMPANION_REVOKED"],
            elder_id=elder_ids["張阿姨"],
            purpose_code="PROACTIVE_COMPANION",
            status="REVOKED",
            version=1,
            scope={},
            granted_by_actor_id=actor_ids["zhang_elder"],
            policy_id=policy_id,
            granted_at=now - timedelta(days=14),
            effective_at=now - timedelta(days=14),
            revoked_at=now - timedelta(days=1),
        )
    )
    await session.flush()

    assignment_id = _id(manifest["assignment"]["陳伯伯今日派案"])
    session.add(
        CareAssignment(
            id=assignment_id,
            tenant_id=home_tenant_id,
            care_unit_id=unit_ids["安心居家服務"],
            elder_id=elder_ids["陳伯伯"],
            worker_id=actor_ids["home_worker"],
            service_start=now - timedelta(hours=1),
            service_end=now + timedelta(hours=7),
            service_scope=[
                "elder:basic:read",
                "assignment:read",
                "assignment:start",
                "assignment:complete",
                "care_event:candidate:create",
                "care_event:read",
                "summary:read",
            ],
            status="CONFIRMED",
            version=1,
        )
    )

    event_ids = {key: _id(value) for key, value in manifest["care_events"].items()}
    event_specs = [
        (
            "林阿嬤早餐",
            "林阿嬤",
            daycare_tenant_id,
            "MEAL",
            {"meal": "早餐吃粥", "data_status": "PRESENT"},
            actor_ids["daycare_worker"],
            1,
        ),
        (
            "林阿嬤等待女兒電話",
            "林阿嬤",
            daycare_tenant_id,
            "SOCIAL_CONTACT",
            {"relationship": "女兒小美", "routine": "每週日通話"},
            actor_ids["lin_elder"],
            1,
        ),
        (
            "陳伯伯居服事件",
            "陳伯伯",
            home_tenant_id,
            "ACTIVITY",
            {"activity": "居家陪伴散步", "data_status": "PRESENT"},
            actor_ids["home_worker"],
            1,
        ),
    ]
    for index, (
        event_key,
        elder_key,
        tenant_id,
        event_type,
        payload,
        creator_id,
        consent_version,
    ) in enumerate(event_specs, start=1):
        event_id = event_ids[event_key]
        session.add(
            CareEvent(
                id=event_id,
                tenant_id=tenant_id,
                elder_id=elder_ids[elder_key],
                event_type=event_type,
                event_time=now - timedelta(hours=index),
                status="VERIFIED",
                current_version=1,
                consent_version=consent_version,
            )
        )
        session.add(
            CareEventVersion(
                event_version_id=_id(f"91000000-0000-4000-8000-{index:012d}"),
                event_id=event_id,
                version=1,
                structured_payload=payload,
                evidence_text_ref=f"synthetic://demo/event/{event_id}",
                created_by_actor_id=creator_id,
            )
        )

    summary_ids = {key: _id(value) for key, value in manifest["summaries"].items()}
    summary_specs = [
        (
            "林阿嬤_READY",
            "林阿嬤",
            daycare_tenant_id,
            "READY",
            [event_ids["林阿嬤早餐"], event_ids["林阿嬤等待女兒電話"]],
            {
                "items": [
                    {
                        "category": "MEAL",
                        "text": "早餐提到吃粥。",
                        "source_event_ids": [str(event_ids["林阿嬤早餐"])],
                        "data_status": "PRESENT",
                    }
                ],
                "missing_fields": ["SLEEP"],
                "conflict_flags": [],
            },
            actor_ids["daycare_worker"],
        ),
        (
            "張阿姨_NEEDS_REVIEW",
            "張阿姨",
            daycare_tenant_id,
            "NEEDS_REVIEW",
            [],
            {"items": [], "missing_fields": ["MEAL", "ACTIVITY"], "conflict_flags": []},
            actor_ids["daycare_worker"],
        ),
        (
            "陳伯伯_READY",
            "陳伯伯",
            home_tenant_id,
            "READY",
            [event_ids["陳伯伯居服事件"]],
            {
                "items": [
                    {
                        "category": "ACTIVITY",
                        "text": "居服期間完成短程散步。",
                        "source_event_ids": [str(event_ids["陳伯伯居服事件"])],
                        "data_status": "PRESENT",
                    }
                ],
                "missing_fields": [],
                "conflict_flags": [],
            },
            actor_ids["home_worker"],
        ),
    ]
    for index, (
        summary_key,
        elder_key,
        tenant_id,
        status,
        source_event_ids,
        content,
        creator_id,
    ) in enumerate(summary_specs, start=1):
        summary_id = summary_ids[summary_key]
        session.add(
            DailySummary(
                id=summary_id,
                tenant_id=tenant_id,
                elder_id=elder_ids[elder_key],
                summary_date=today,
                summary_type="PROFESSIONAL_DAILY",
                status=status,
                current_version=1,
                generated_at=now,
            )
        )
        session.add(
            SummaryVersion(
                summary_version_id=_id(f"92100000-0000-4000-8000-{index:012d}"),
                summary_id=summary_id,
                version=1,
                content=content,
                source_event_ids=source_event_ids,
                model_version="synthetic-seed-v1",
                prompt_version="synthetic-seed-v1",
                created_by_actor_id=creator_id,
            )
        )

    memory_id = _id(manifest["memory"]["林阿嬤_女兒每週日通話_ACTIVE"])
    memory_version_id = _id("93100000-0000-4000-8000-000000000001")
    session.add(
        Memory(
            id=memory_id,
            tenant_id=daycare_tenant_id,
            elder_id=elder_ids["林阿嬤"],
            memory_type="IMPORTANT_RELATIONSHIP",
            status="ACTIVE",
            current_version=1,
            confirmed_by_actor_id=actor_ids["lin_elder"],
            confirmed_at=now - timedelta(days=1),
            activated_at=now - timedelta(days=1),
            consent_version=1,
        )
    )
    session.add(
        MemoryVersion(
            memory_version_id=memory_version_id,
            memory_id=memory_id,
            version=1,
            content="林阿嬤每週日會等女兒小美打電話。",
            source_event_ids=[event_ids["林阿嬤等待女兒電話"]],
            version_status="ACTIVE",
            valid_from=now - timedelta(days=1),
            created_by_actor_id=actor_ids["lin_elder"],
        )
    )

    family_relationship_id = _id(manifest["family_relationship"]["陳伯伯家屬"])
    session.add(
        FamilyRelationship(
            id=family_relationship_id,
            elder_id=elder_ids["陳伯伯"],
            family_actor_id=actor_ids["chen_family"],
            share_scope=["REPORT_ALL"],
            status="ACTIVE",
            effective_from=now - timedelta(days=7),
            consent_id=consent_ids["陳伯伯_FAMILY_SHARING"],
        )
    )

    report_ids = {key: _id(value) for key, value in manifest["reports"].items()}
    report_statuses = [
        ("draft", "DAILY", today, today, "DRAFT"),
        ("published", "WEEKLY", today - timedelta(days=6), today, "PUBLISHED"),
        ("withdrawn", "MONTHLY", today - timedelta(days=29), today, "WITHDRAWN"),
    ]
    report_version_ids: dict[str, UUID] = {}
    for index, (report_key, report_type, period_start, period_end, status) in enumerate(
        report_statuses,
        start=1,
    ):
        report_id = report_ids[report_key]
        report_version_id = _id(f"95100000-0000-4000-8000-{index:012d}")
        report_version_ids[report_key] = report_version_id
        session.add(
            FamilyReport(
                id=report_id,
                tenant_id=home_tenant_id,
                elder_id=elder_ids["陳伯伯"],
                recipient_scope={"relationship_ids": [str(family_relationship_id)]},
                report_type=report_type,
                period_start=period_start,
                period_end=period_end,
                status=status,
                current_version=1,
                created_by_actor_id=actor_ids["home_worker"],
                published_at=now - timedelta(hours=2)
                if status in {"PUBLISHED", "WITHDRAWN"}
                else None,
                withdrawn_at=now - timedelta(hours=1) if status == "WITHDRAWN" else None,
            )
        )
        session.add(
            ReportVersion(
                report_version_id=report_version_id,
                report_id=report_id,
                version=1,
                content={
                    "items": [
                        {
                            "category": "ACTIVITY",
                            "text": "本期有完成居家陪伴散步。",
                            "source_ids": [str(summary_ids["陳伯伯_READY"])],
                        }
                    ],
                    "data_gap_notice": None,
                    "sensitive_review_required": True,
                },
                source_summary_ids=[summary_ids["陳伯伯_READY"]],
                source_event_ids=[event_ids["陳伯伯居服事件"]],
                share_scope_snapshot={"relationship_ids": [str(family_relationship_id)]},
                created_by_actor_id=actor_ids["home_worker"],
            )
        )

    outbox_id = _id(manifest["outbox"]["memory_confirmed"])
    session.add(
        OutboxEvent(
            outbox_event_id=outbox_id,
            event_id=_id("98100000-0000-4000-8000-000000000001"),
            event_type="memory.confirmed.v1",
            aggregate_type="memory",
            aggregate_id=memory_id,
            aggregate_version=1,
            tenant_id=daycare_tenant_id,
            elder_id=elder_ids["林阿嬤"],
            actor_id=actor_ids["lin_elder"],
            purpose="LONG_TERM_MEMORY",
            consent_version=1,
            trace_id="synthetic-seed-memory-confirmed",
            correlation_id="synthetic-seed-memory-confirmed",
            idempotency_key="synthetic-seed-memory-confirmed",
            classification="CONFIDENTIAL",
            payload={
                "memory_id": str(memory_id),
                "status": "ACTIVE",
                "version": 1,
            },
            delivery_status="PENDING",
            occurred_at=now - timedelta(days=1),
        )
    )
    await session.flush()

    await session.execute(
        text(
            """
            INSERT INTO eldercare_ai.notification_preference (
                preference_id, family_actor_id, elder_id, channels, frequency,
                send_time_local, timezone, quiet_hours, important_event_enabled, status
            ) VALUES (
                :preference_id, :family_actor_id, :elder_id,
                ARRAY['EMAIL']::eldercare_ai.notification_channel_enum[],
                'DAILY', '18:00', 'Asia/Taipei',
                '{"start":"21:00","end":"08:00"}'::jsonb, true, 'ACTIVE'
            )
            """
        ),
        {
            "preference_id": _id("96000000-0000-4000-8000-000000000010"),
            "family_actor_id": actor_ids["chen_family"],
            "elder_id": elder_ids["陳伯伯"],
        },
    )
    notification_ids = {key: _id(value) for key, value in manifest["notifications"].items()}
    for notification_key, status, attempt_count, last_error in [
        ("sent", "SENT", 1, None),
        ("failed_retryable", "FAILED", 2, "DEMO_ADAPTER_UNAVAILABLE"),
    ]:
        await session.execute(
            text(
                """
                INSERT INTO eldercare_ai.notification_delivery (
                    notification_id, report_id, report_version_id,
                    recipient_actor_id, preference_id, channel, status,
                    scheduled_at, sent_at, attempt_count, last_error, idempotency_key
                ) VALUES (
                    :notification_id, :report_id, :report_version_id,
                    :recipient_actor_id, :preference_id, 'EMAIL', :status,
                    :scheduled_at, :sent_at, :attempt_count, :last_error,
                    :idempotency_key
                )
                """
            ),
            {
                "notification_id": notification_ids[notification_key],
                "report_id": report_ids["published"],
                "report_version_id": report_version_ids["published"],
                "recipient_actor_id": actor_ids["chen_family"],
                "preference_id": _id("96000000-0000-4000-8000-000000000010"),
                "status": status,
                "scheduled_at": now - timedelta(hours=1),
                "sent_at": now - timedelta(minutes=55) if status == "SENT" else None,
                "attempt_count": attempt_count,
                "last_error": last_error,
                "idempotency_key": f"synthetic-notification-{notification_key}",
            },
        )

    await session.execute(
        text(
            """
            INSERT INTO eldercare_ai.graph_projection_record (
                projection_id, source_type, source_id, source_version,
                projection_status, attempt_count, last_error
            ) VALUES (
                :projection_id, 'MEMORY', :source_id, 1,
                'FAILED', 2, 'DEMO_GRAPH_UNAVAILABLE'
            )
            """
        ),
        {
            "projection_id": _id(manifest["faults"]["graph_unavailable"]),
            "source_id": memory_id,
        },
    )


async def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("synthetic_only") is not True:
        raise RuntimeError("Seed manifest must declare synthetic_only=true")
    engine = create_async_engine(_database_url())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                await _seed(session, manifest)
    finally:
        await engine.dispose()
    print(
        json.dumps(
            {
                "ok": True,
                "synthetic_only": True,
                "manifest": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
                "elder_ids": manifest["elders"],
                "report_ids": manifest["reports"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

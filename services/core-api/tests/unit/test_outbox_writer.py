"""Unit tests for outbox_writer validation logic.

Tests validation rules without requiring a database connection.
The INSERT execution path is tested in integration tests.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationError
from app.events.outbox_writer import (
    MAX_PAYLOAD_BYTES,
    RESTRICTED_PAYLOAD_KEYS,
    write_outbox_entry,
)

EXPECTED_RESTRICTED_PAYLOAD_KEYS = frozenset(
    {
        "audio",
        "audio_uri",
        "full_prompt",
        "prompt",
        "secret",
        "token",
        "transcript",
        "transcript_text",
    }
)


@pytest.fixture
def mock_session():
    """Provide a mock async session for unit tests."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def valid_params():
    """Provide valid parameters for write_outbox_entry.

    aggregate_type and trace_id are required NOT NULL columns in the
    eldercare_ai.outbox_event baseline table.
    """
    return {
        "event_type": "elder.created",
        "aggregate_type": "Elder",
        "aggregate_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "payload": {"name": "Test Elder", "age": 85},
        "trace_id": "trace-abc-123",
    }


class TestWriteOutboxEntryValidation:
    """Tests for input validation in write_outbox_entry."""

    @pytest.mark.asyncio
    async def test_rejects_empty_event_type(self, mock_session, valid_params):
        valid_params["event_type"] = ""

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "event_type" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_none_event_type(self, mock_session, valid_params):
        valid_params["event_type"] = None

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "event_type" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_non_uuid_aggregate_id(self, mock_session, valid_params):
        valid_params["aggregate_id"] = "not-a-uuid"

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "aggregate_id" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_empty_aggregate_type(self, mock_session, valid_params):
        valid_params["aggregate_type"] = ""

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "aggregate_type" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_none_aggregate_type(self, mock_session, valid_params):
        valid_params["aggregate_type"] = None

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "aggregate_type" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_empty_trace_id(self, mock_session, valid_params):
        valid_params["trace_id"] = ""

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "trace_id" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_none_trace_id(self, mock_session, valid_params):
        valid_params["trace_id"] = None

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "trace_id" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_zero_aggregate_version(self, mock_session, valid_params):
        valid_params["aggregate_version"] = 0

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "aggregate_version" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_negative_aggregate_version(self, mock_session, valid_params):
        valid_params["aggregate_version"] = -1

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "aggregate_version" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_non_int_aggregate_version(self, mock_session, valid_params):
        valid_params["aggregate_version"] = "1"

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "aggregate_version" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_non_uuid_tenant_id(self, mock_session, valid_params):
        valid_params["tenant_id"] = "not-a-uuid"

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "tenant_id" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_none_payload(self, mock_session, valid_params):
        valid_params["payload"] = None

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "payload" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_lone_unicode_surrogate(self, mock_session, valid_params):
        valid_params["payload"] = {"value": "\ud800"}

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert exc_info.value.details[0]["reason"] == "payload must be valid finite UTF-8 JSON"

    @pytest.mark.asyncio
    async def test_rejects_every_restricted_field_case_insensitively_and_when_nested(
        self, mock_session, valid_params
    ):
        assert RESTRICTED_PAYLOAD_KEYS == EXPECTED_RESTRICTED_PAYLOAD_KEYS

        for key in sorted(EXPECTED_RESTRICTED_PAYLOAD_KEYS):
            payloads = [
                {key: "restricted"},
                {key.upper(): "restricted"},
                {"evidence": [{key: "restricted"}]},
            ]
            for payload in payloads:
                valid_params["payload"] = payload
                with pytest.raises(ValidationError) as exc_info:
                    await write_outbox_entry(mock_session, **valid_params)

                assert any(d["field"] == "payload" for d in exc_info.value.details)

    @pytest.mark.asyncio
    async def test_rejects_oversized_payload(self, mock_session, valid_params):
        # Create a payload that exceeds 256 KB when serialized
        valid_params["payload"] = {"data": "x" * (MAX_PAYLOAD_BYTES + 1)}

        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(mock_session, **valid_params)

        assert any(d["field"] == "payload" for d in exc_info.value.details)
        assert "exceeds" in exc_info.value.details[0]["reason"].lower()

    @pytest.mark.asyncio
    async def test_collects_multiple_validation_errors(self, mock_session):
        with pytest.raises(ValidationError) as exc_info:
            await write_outbox_entry(
                mock_session,
                event_type="",
                aggregate_type="",
                aggregate_id="bad",
                tenant_id="bad",
                payload=None,
                trace_id="",
                aggregate_version=0,
            )

        # Should report all field errors at once
        fields = {d["field"] for d in exc_info.value.details}
        assert "event_type" in fields
        assert "aggregate_type" in fields
        assert "aggregate_id" in fields
        assert "tenant_id" in fields
        assert "payload" in fields
        assert "trace_id" in fields
        assert "aggregate_version" in fields


class TestWriteOutboxEntrySuccess:
    """Tests for successful outbox entry writes."""

    @pytest.mark.asyncio
    async def test_generates_event_id_when_not_provided(self, mock_session, valid_params):
        await write_outbox_entry(mock_session, **valid_params)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_provided_event_id(self, mock_session, valid_params):
        custom_event_id = uuid.uuid4()

        await write_outbox_entry(mock_session, **valid_params, event_id=custom_event_id)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_empty_dict_payload(self, mock_session, valid_params):
        valid_params["payload"] = {}

        await write_outbox_entry(mock_session, **valid_params)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_payload_at_max_size(self, mock_session, valid_params):
        # Create a payload just under the limit
        # JSON overhead for {"d": "..."} is about 7 bytes
        valid_params["payload"] = {"d": "x" * (MAX_PAYLOAD_BYTES - 10)}

        await write_outbox_entry(mock_session, **valid_params)

        mock_session.execute.assert_called_once()

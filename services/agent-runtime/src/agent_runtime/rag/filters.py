from __future__ import annotations

from collections.abc import Mapping

from agent_runtime.rag.models import QueryProfile


def build_normal_rag_filter(
    *,
    profile: QueryProfile,
    audience: str | None = None,
    purpose: str | None = None,
) -> dict[str, object]:
    """Return mandatory fail-closed filters for ordinary RAG answers."""

    must: list[dict[str, object]] = [
        {"term": {"current_status": "current"}},
        {"term": {"stop_normal_rag": False}},
    ]
    must.append(_scope_filter("allowed_audiences", audience))
    must.append(_scope_filter("allowed_purposes", purpose))
    bool_filter: dict[str, object] = {
        "must": must,
        "must_not": [
            {"terms": {"risk_level": ["high", "critical", "high_red_line"]}},
        ],
    }
    return {"bool": bool_filter}


def is_normal_rag_eligible(
    source: Mapping[str, object],
    profile: QueryProfile,
    *,
    audience: str | None = None,
    purpose: str | None = None,
) -> bool:
    """Defence-in-depth after search; missing policy fields are denied."""

    if source.get("current_status") != "current":
        return False
    if source.get("stop_normal_rag") is not False:
        return False
    risk_level = source.get("risk_level")
    if isinstance(risk_level, str) and risk_level.casefold() in {
        "high",
        "critical",
        "high_red_line",
    }:
        return False
    if not _scope_allows(source.get("allowed_audiences"), audience):
        return False
    if not _scope_allows(source.get("allowed_purposes"), purpose):
        return False
    return True


def _scope_allows(raw_allowed: object, requested: str | None) -> bool:
    if raw_allowed is None:
        return True
    if not isinstance(raw_allowed, list) or any(
        not isinstance(value, str) for value in raw_allowed
    ):
        return False
    if not raw_allowed:
        return True
    return requested is not None and requested in raw_allowed


def _scope_filter(field: str, requested: str | None) -> dict[str, object]:
    """Allow an explicit scope match or an absent/empty unrestricted field."""

    unrestricted = {"bool": {"must_not": [{"exists": {"field": field}}]}}
    if requested is None:
        return unrestricted
    return {
        "bool": {
            "should": [
                {"term": {field: requested}},
                unrestricted,
            ],
            "minimum_should_match": 1,
        }
    }

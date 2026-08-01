"""Safety boundaries for the deterministic demo seed target."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


def _load_seed_module() -> ModuleType:
    path = Path(__file__).resolve().parents[4] / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("seed_demo_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEED_DEMO = _load_seed_module()


def _environment(database_url: str, *, allow_e2e: bool = False) -> dict[str, str]:
    return {
        "APP_ENV": "development",
        "DATABASE_URL": database_url,
        "KINSUN_ALLOW_SYNTHETIC_E2E_SEED": str(allow_e2e).lower(),
    }


def test_default_local_demo_database_is_allowed() -> None:
    value = "postgresql+asyncpg://user:pass@127.0.0.1:5432/kinsun"
    with patch.dict(os.environ, _environment(value), clear=True):
        assert SEED_DEMO._database_url() == value


def test_synthetic_e2e_database_requires_explicit_opt_in() -> None:
    value = "postgresql+asyncpg://user:pass@127.0.0.1:5432/kinsun_frontend_e2e_test"
    with patch.dict(os.environ, _environment(value), clear=True):
        with pytest.raises(RuntimeError, match="KINSUN_ALLOW_SYNTHETIC_E2E_SEED"):
            SEED_DEMO._database_url()

    with patch.dict(os.environ, _environment(value, allow_e2e=True), clear=True):
        assert SEED_DEMO._database_url() == value


def test_remote_database_is_rejected_even_with_e2e_opt_in() -> None:
    value = "postgresql+asyncpg://user:pass@db.example.test/kinsun_frontend_e2e_test"
    with patch.dict(os.environ, _environment(value, allow_e2e=True), clear=True):
        with pytest.raises(RuntimeError, match="restricted to local"):
            SEED_DEMO._database_url()

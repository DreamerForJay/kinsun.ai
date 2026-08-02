"""Static safety contract for the Core API and migration container images."""

from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (SERVICE_ROOT / name).read_text(encoding="utf-8")


def test_api_image_is_non_root_production_runtime() -> None:
    dockerfile = _read("Dockerfile.api")

    assert 'LABEL io.kinsun.artifact="core-api"' in dockerfile
    assert "APP_ENV=production" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert dockerfile.index("USER 10001:10001") < dockerfile.index('CMD ["uvicorn"')
    assert 'ENTRYPOINT ["python", "-m", "app.container_entrypoint", "postgresql+asyncpg"]' in (
        dockerfile
    )
    assert 'CMD ["uvicorn", "app.main:app"' in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "http://127.0.0.1:8000/health" in dockerfile


def test_api_image_copies_only_runtime_source() -> None:
    dockerfile = _read("Dockerfile.api")

    assert "COPY --chown=10001:10001 app ./app" in dockerfile
    assert "COPY ." not in dockerfile
    assert "alembic upgrade head" not in dockerfile


def test_migration_image_remains_a_one_shot_alembic_job() -> None:
    dockerfile = _read("Dockerfile")

    assert 'LABEL io.kinsun.artifact="core-migration"' in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert dockerfile.index("USER 10001:10001") < dockerfile.index('CMD ["python"')
    assert "COPY --chown=10001:10001 alembic.ini ./" in dockerfile
    assert "COPY --chown=10001:10001 alembic ./alembic" in dockerfile
    assert "COPY --chown=10001:10001 app ./app" in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "app.container_entrypoint", "postgresql+psycopg"]' in (
        dockerfile
    )
    assert 'CMD ["python", "-m", "app.migration_job"]' in dockerfile
    assert 'CMD ["uvicorn"' not in dockerfile


def test_docker_context_excludes_local_secrets_and_tests() -> None:
    ignored = {
        line.strip()
        for line in _read(".dockerignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {".env", ".env.*", ".venv/", "tests/"} <= ignored

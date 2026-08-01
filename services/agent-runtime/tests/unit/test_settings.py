from pathlib import Path

from agent_runtime.settings import AGENT_RUNTIME_ENV_FILE, REPOSITORY_ENV_FILE, Settings


def test_env_files_are_absolute_and_service_scoped_last() -> None:
    """Staging RAG settings live in the repository-root .env, so both are read.

    Every entry stays absolute: a working-directory-relative ".env" would make
    the loaded configuration depend on where the process happens to start.
    """

    service_env = Path(__file__).resolve().parents[2] / ".env"
    repository_env = Path(__file__).resolve().parents[4] / ".env"

    assert AGENT_RUNTIME_ENV_FILE == service_env
    assert REPOSITORY_ENV_FILE == repository_env

    env_files = Settings.model_config["env_file"]
    assert env_files == (REPOSITORY_ENV_FILE, AGENT_RUNTIME_ENV_FILE)
    assert all(isinstance(path, Path) and path.is_absolute() for path in env_files)
    # pydantic-settings gives the last file priority, so the service keeps the
    # final say over anything shared at the repository root.
    assert env_files[-1] == AGENT_RUNTIME_ENV_FILE

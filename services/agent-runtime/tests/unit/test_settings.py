from pathlib import Path

from agent_runtime.settings import AGENT_RUNTIME_ENV_FILE, Settings


def test_env_file_is_service_scoped_and_absolute() -> None:
    expected = Path(__file__).resolve().parents[2] / ".env"

    assert AGENT_RUNTIME_ENV_FILE == expected
    assert AGENT_RUNTIME_ENV_FILE.is_absolute()
    assert Settings.model_config["env_file"] == expected

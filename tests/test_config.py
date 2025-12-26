import os
import tempfile
from devlogs import config

def test_load_config_defaults(monkeypatch):
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    for key in (
        "DEVLOGS_OPENSEARCH_HOST",
        "DEVLOGS_OPENSEARCH_PORT",
        "DEVLOGS_OPENSEARCH_USER",
        "DEVLOGS_OPENSEARCH_PASS",
        "DEVLOGS_OPENSEARCH_TIMEOUT",
        "DEVLOGS_INDEX_LOGS",
        "DEVLOGS_RETENTION_DEBUG_HOURS",
        "DEVLOGS_AREA_DEFAULT",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = config.load_config()
    assert cfg.opensearch_host == "localhost"
    assert cfg.opensearch_port == 9200
    assert cfg.opensearch_user == "admin"
    assert cfg.opensearch_pass == "admin"

def test_set_dotenv_path(monkeypatch):
    """Test that set_dotenv_path() sets custom env file path."""
    # Reset config state
    monkeypatch.setattr(config, "_dotenv_loaded", False)
    monkeypatch.setattr(config, "_custom_dotenv_path", None)
    # Clear any environment variables that might interfere
    for key in ("DEVLOGS_OPENSEARCH_HOST", "DEVLOGS_OPENSEARCH_PORT", "DEVLOGS_INDEX_LOGS", "DOTENV_PATH"):
        monkeypatch.delenv(key, raising=False)

    # Create a temporary .env file with custom values
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("DEVLOGS_OPENSEARCH_HOST=custom-host\n")
        f.write("DEVLOGS_OPENSEARCH_PORT=9999\n")
        f.write("DEVLOGS_INDEX_LOGS=custom-index\n")
        temp_env_path = f.name

    try:
        # Set the custom dotenv path
        config.set_dotenv_path(temp_env_path)

        # Load config and verify it uses the custom values
        cfg = config.load_config()
        assert cfg.opensearch_host == "custom-host"
        assert cfg.opensearch_port == 9999
        assert cfg.index_logs == "custom-index"
    finally:
        # Clean up
        os.unlink(temp_env_path)
        monkeypatch.setattr(config, "_dotenv_loaded", False)
        monkeypatch.setattr(config, "_custom_dotenv_path", None)

def test_dotenv_path_environment_variable(monkeypatch):
    """Test that DOTENV_PATH environment variable works."""
    # Reset config state
    monkeypatch.setattr(config, "_dotenv_loaded", False)
    monkeypatch.setattr(config, "_custom_dotenv_path", None)
    # Clear any environment variables that might interfere
    for key in ("DEVLOGS_OPENSEARCH_HOST", "DEVLOGS_OPENSEARCH_PORT", "DEVLOGS_INDEX_LOGS", "DOTENV_PATH"):
        monkeypatch.delenv(key, raising=False)

    # Create a temporary .env file with custom values
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("DEVLOGS_OPENSEARCH_HOST=env-var-host\n")
        f.write("DEVLOGS_OPENSEARCH_PORT=8888\n")
        f.write("DEVLOGS_INDEX_LOGS=env-var-index\n")
        temp_env_path = f.name

    try:
        # Set DOTENV_PATH environment variable
        monkeypatch.setenv("DOTENV_PATH", temp_env_path)

        # Load config and verify it uses the custom values
        cfg = config.load_config()
        assert cfg.opensearch_host == "env-var-host"
        assert cfg.opensearch_port == 8888
        assert cfg.index_logs == "env-var-index"
    finally:
        # Clean up
        os.unlink(temp_env_path)
        monkeypatch.delenv("DOTENV_PATH", raising=False)
        monkeypatch.setattr(config, "_dotenv_loaded", False)
        monkeypatch.setattr(config, "_custom_dotenv_path", None)

def test_set_dotenv_path_resets_loaded_flag(monkeypatch):
    """Test that set_dotenv_path() resets the loaded flag to allow reload."""
    # Set up initial state as loaded
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.setattr(config, "_custom_dotenv_path", None)

    # Call set_dotenv_path
    config.set_dotenv_path("/path/to/custom.env")

    # Verify the flag was reset
    assert config._dotenv_loaded == False
    assert config._custom_dotenv_path == "/path/to/custom.env"

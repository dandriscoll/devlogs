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
        "DEVLOGS_INDEX",
        "DEVLOGS_RETENTION_DEBUG",
        "DEVLOGS_RETENTION_INFO",
        "DEVLOGS_RETENTION_WARNING",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = config.load_config()
    assert cfg.opensearch_host == "localhost"
    assert cfg.opensearch_port == 9200
    assert cfg.opensearch_user == "admin"
    assert cfg.opensearch_pass == "admin"
    assert cfg.retention_debug_hours == 6
    assert cfg.retention_info_days == 7
    assert cfg.retention_warning_days == 30

def test_set_dotenv_path(monkeypatch):
    """Test that set_dotenv_path() sets custom env file path."""
    # Reset config state
    monkeypatch.setattr(config, "_dotenv_loaded", False)
    monkeypatch.setattr(config, "_custom_dotenv_path", None)
    # Clear any environment variables that might interfere
    for key in ("DEVLOGS_OPENSEARCH_HOST", "DEVLOGS_OPENSEARCH_PORT", "DEVLOGS_INDEX", "DOTENV_PATH"):
        monkeypatch.delenv(key, raising=False)

    # Create a temporary .env file with custom values
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("DEVLOGS_OPENSEARCH_HOST=custom-host\n")
        f.write("DEVLOGS_OPENSEARCH_PORT=9999\n")
        f.write("DEVLOGS_INDEX=custom-index\n")
        temp_env_path = f.name

    try:
        # Set the custom dotenv path
        config.set_dotenv_path(temp_env_path)

        # Load config and verify it uses the custom values
        cfg = config.load_config()
        assert cfg.opensearch_host == "custom-host"
        assert cfg.opensearch_port == 9999
        assert cfg.index == "custom-index"
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
    for key in ("DEVLOGS_OPENSEARCH_HOST", "DEVLOGS_OPENSEARCH_PORT", "DEVLOGS_INDEX", "DOTENV_PATH"):
        monkeypatch.delenv(key, raising=False)

    # Create a temporary .env file with custom values
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("DEVLOGS_OPENSEARCH_HOST=env-var-host\n")
        f.write("DEVLOGS_OPENSEARCH_PORT=8888\n")
        f.write("DEVLOGS_INDEX=env-var-index\n")
        temp_env_path = f.name

    try:
        # Set DOTENV_PATH environment variable
        monkeypatch.setenv("DOTENV_PATH", temp_env_path)

        # Load config and verify it uses the custom values
        cfg = config.load_config()
        assert cfg.opensearch_host == "env-var-host"
        assert cfg.opensearch_port == 8888
        assert cfg.index == "env-var-index"
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

def test_parse_duration_hours():
    """Test parse_duration with hour values."""
    assert config.parse_duration("6h", unit="hours") == 6
    assert config.parse_duration("24H", unit="hours") == 24
    assert config.parse_duration("12", unit="hours") == 12  # Plain number
    # Days to hours conversion
    assert config.parse_duration("1d", unit="hours") == 24
    assert config.parse_duration("2D", unit="hours") == 48

def test_parse_duration_days():
    """Test parse_duration with day values."""
    assert config.parse_duration("7d", unit="days") == 7
    assert config.parse_duration("30D", unit="days") == 30
    assert config.parse_duration("14", unit="days") == 14  # Plain number
    # Hours to days conversion (rounds up)
    assert config.parse_duration("24h", unit="days") == 1
    assert config.parse_duration("25h", unit="days") == 2
    assert config.parse_duration("48H", unit="days") == 2

def test_parse_duration_invalid():
    """Test parse_duration with invalid formats."""
    import pytest
    with pytest.raises(ValueError, match="Invalid duration format"):
        config.parse_duration("abc", unit="hours")
    with pytest.raises(ValueError, match="Invalid duration format"):
        config.parse_duration("12x", unit="hours")


def test_parse_duration_empty_returns_zero():
    """Test parse_duration returns 0 for empty/None values."""
    assert config.parse_duration("", unit="hours") == 0

def test_retention_duration_strings(monkeypatch):
    """Test that retention config accepts duration strings."""
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.setenv("DEVLOGS_RETENTION_DEBUG", "12h")
    monkeypatch.setenv("DEVLOGS_RETENTION_INFO", "14d")
    monkeypatch.setenv("DEVLOGS_RETENTION_WARNING", "60d")

    cfg = config.load_config()
    assert cfg.retention_debug_hours == 12
    assert cfg.retention_info_days == 14
    assert cfg.retention_warning_days == 60

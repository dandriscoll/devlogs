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
    assert cfg.enabled is False
    assert cfg.opensearch_host == "localhost"
    assert cfg.opensearch_port == 9200
    assert cfg.opensearch_user == "admin"
    assert cfg.opensearch_pass == "admin"
    assert cfg.retention_debug_hours == 6
    assert cfg.retention_info_days == 7
    assert cfg.retention_warning_days == 30


def test_load_config_enabled_with_any_setting(monkeypatch):
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
    monkeypatch.setenv("DEVLOGS_INDEX", "devlogs-enabled-test")
    cfg = config.load_config()
    assert cfg.enabled is True
    assert cfg.index == "devlogs-enabled-test"


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


# URL format tests

def test_parse_opensearch_url_with_index():
    """Test URL parsing extracts index from path."""
    result = config._parse_opensearch_url("https://admin:pass@host:9200/myindex")
    assert result == ("https", "host", 9200, "admin", "pass", "myindex")


def test_parse_opensearch_url_without_index():
    """Test URL parsing returns None for index when path is empty."""
    result = config._parse_opensearch_url("https://admin:pass@host:9200")
    assert result == ("https", "host", 9200, "admin", "pass", None)


def test_parse_opensearch_url_with_trailing_slash():
    """Test URL parsing handles trailing slash correctly."""
    result = config._parse_opensearch_url("https://admin:pass@host:9200/")
    assert result == ("https", "host", 9200, "admin", "pass", None)


def test_parse_opensearch_url_no_auth():
    """Test URL parsing without credentials."""
    result = config._parse_opensearch_url("http://localhost:9200/devlogs-prod")
    assert result == ("http", "localhost", 9200, None, None, "devlogs-prod")


def test_parse_opensearch_url_https_default_port():
    """Test URL parsing uses port 443 for https when not specified."""
    result = config._parse_opensearch_url("https://host/index")
    assert result == ("https", "host", 443, None, None, "index")


def test_parse_opensearch_url_empty():
    """Test URL parsing returns None for empty input."""
    assert config._parse_opensearch_url("") is None
    assert config._parse_opensearch_url(None) is None


def test_config_index_from_url(monkeypatch):
    """Test that index in URL takes priority over DEVLOGS_INDEX."""
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "https://admin:pass@host:9200/url-index")
    monkeypatch.setenv("DEVLOGS_INDEX", "env-index")

    cfg = config.load_config()
    assert cfg.index == "url-index"


def test_config_index_fallback_to_env(monkeypatch):
    """Test that DEVLOGS_INDEX is used when URL has no index."""
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "https://admin:pass@host:9200")
    monkeypatch.setenv("DEVLOGS_INDEX", "env-index")

    cfg = config.load_config()
    assert cfg.index == "env-index"


def test_config_index_fallback_to_default(monkeypatch):
    """Test that default index is used when neither URL nor env var specify one."""
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "https://admin:pass@host:9200")
    monkeypatch.delenv("DEVLOGS_INDEX", raising=False)

    cfg = config.load_config()
    assert cfg.index == "devlogs-0001"


def test_parse_opensearch_url_decodes_password():
    """Test URL parsing decodes URL-encoded password."""
    # Password with ! encoded as %21
    result = config._parse_opensearch_url("https://admin:mX4Vst2s%21@host:9200/index")
    assert result[3] == "admin"  # username
    assert result[4] == "mX4Vst2s!"  # password should be decoded


def test_parse_opensearch_url_decodes_username():
    """Test URL parsing decodes URL-encoded username."""
    # Username with @ encoded as %40
    result = config._parse_opensearch_url("https://user%40domain:pass@host:9200/index")
    assert result[3] == "user@domain"  # username should be decoded
    assert result[4] == "pass"


def test_parse_opensearch_url_decodes_special_characters():
    """Test URL parsing decodes various special characters in credentials."""
    # Test multiple special characters: ! @ # $ % ^ & * ( ) encoded
    result = config._parse_opensearch_url(
        "https://user%21%40:pass%23%24%25@host:9200/index"
    )
    assert result[3] == "user!@"  # username with ! and @
    assert result[4] == "pass#$%"  # password with # $ %


def test_parse_opensearch_url_handles_plus_sign():
    """Test URL parsing decodes + as space (standard URL encoding)."""
    result = config._parse_opensearch_url("https://user:pass%2Bword@host:9200/index")
    assert result[4] == "pass+word"  # %2B is +


def test_parse_opensearch_url_handles_colon_in_password():
    """Test URL parsing handles encoded colon in password."""
    result = config._parse_opensearch_url("https://admin:pass%3Aword@host:9200/index")
    assert result[4] == "pass:word"  # %3A is :


def test_parse_opensearch_url_handles_slash_in_password():
    """Test URL parsing handles encoded slash in password."""
    result = config._parse_opensearch_url("https://admin:pass%2Fword@host:9200/index")
    assert result[4] == "pass/word"  # %2F is /


def test_set_url(monkeypatch):
    """Test that set_url() sets the URL environment variable."""
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    # Clear any existing URL
    monkeypatch.delenv("DEVLOGS_OPENSEARCH_URL", raising=False)
    monkeypatch.delenv("DEVLOGS_INDEX", raising=False)

    # Save original value to restore later
    original_url = os.environ.get("DEVLOGS_OPENSEARCH_URL")

    try:
        # Set URL via set_url()
        config.set_url("https://myuser:mypass@myhost:9200/myindex")

        # Load config and verify it uses the URL values
        cfg = config.load_config()
        assert cfg.opensearch_scheme == "https"
        assert cfg.opensearch_host == "myhost"
        assert cfg.opensearch_port == 9200
        assert cfg.opensearch_user == "myuser"
        assert cfg.opensearch_pass == "mypass"
        assert cfg.index == "myindex"
    finally:
        # Clean up the environment variable set by set_url()
        if original_url is None:
            os.environ.pop("DEVLOGS_OPENSEARCH_URL", None)
        else:
            os.environ["DEVLOGS_OPENSEARCH_URL"] = original_url


def test_set_url_works_after_dotenv_loaded(monkeypatch):
    """Test that set_url() works even after dotenv has been loaded."""
    # Set up initial state as loaded (simulating dotenv already loaded)
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.delenv("DEVLOGS_OPENSEARCH_URL", raising=False)
    monkeypatch.delenv("DEVLOGS_INDEX", raising=False)

    # Save original value to restore later
    original_url = os.environ.get("DEVLOGS_OPENSEARCH_URL")

    try:
        # Call set_url - this should still work because it sets the env var directly
        config.set_url("https://late:user@latehost:9200/lateindex")

        # Load config and verify it uses the URL values
        cfg = config.load_config()
        assert cfg.opensearch_host == "latehost"
        assert cfg.opensearch_user == "late"
        assert cfg.index == "lateindex"
    finally:
        # Clean up the environment variable set by set_url()
        if original_url is None:
            os.environ.pop("DEVLOGS_OPENSEARCH_URL", None)
        else:
            os.environ["DEVLOGS_OPENSEARCH_URL"] = original_url

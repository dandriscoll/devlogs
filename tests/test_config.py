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

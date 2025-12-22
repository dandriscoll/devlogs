from devlogs import config

def test_load_config_defaults():
    cfg = config.load_config()
    assert cfg.opensearch_host == "localhost"
    assert cfg.opensearch_port == 9200
    assert cfg.opensearch_user == "admin"
    assert cfg.opensearch_pass == "admin"

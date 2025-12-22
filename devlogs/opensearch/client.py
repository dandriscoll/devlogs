# OpenSearch client factory and retry logic

from opensearchpy import OpenSearch
from ..config import load_config

def get_opensearch_client():
	cfg = load_config()
	return OpenSearch(
		hosts=[{"host": cfg.opensearch_host, "port": cfg.opensearch_port}],
		http_auth=(cfg.opensearch_user, cfg.opensearch_pass),
		use_ssl=False,
		verify_certs=False,
	)

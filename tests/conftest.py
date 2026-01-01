import os
import sys
import uuid

import pytest
import warnings


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
	sys.path.insert(0, SRC_DIR)

from devlogs.opensearch.client import get_opensearch_client
from devlogs.opensearch.mappings import LOG_INDEX_TEMPLATE


@pytest.fixture(scope="session")
def opensearch_client():
	try:
		client = get_opensearch_client()
		client.info()
		return client
	except Exception as exc:
		pytest.skip(f"OpenSearch not available: {exc}")


@pytest.fixture()
def test_index(opensearch_client):
	legacy_template_created = False
	try:
		opensearch_client.indices.delete_template(name="devlogs-logs-template")
	except Exception:
		pass
	try:
		opensearch_client.indices.put_index_template(
			name="devlogs-logs-template",
			body=LOG_INDEX_TEMPLATE,
		)
	except Exception:
		legacy_body = {
			"index_patterns": LOG_INDEX_TEMPLATE["index_patterns"],
			"settings": LOG_INDEX_TEMPLATE["template"]["settings"],
			"mappings": LOG_INDEX_TEMPLATE["template"]["mappings"],
		}
		opensearch_client.indices.put_template(
			name="devlogs-logs-template",
			body=legacy_body,
		)
		legacy_template_created = True
	index_name = f"devlogs-logs-test-{uuid.uuid4().hex}"
	if not opensearch_client.indices.exists(index=index_name):
		opensearch_client.indices.create(index=index_name)
	previous_index = os.getenv("DEVLOGS_INDEX")
	os.environ["DEVLOGS_INDEX"] = index_name
	yield index_name
	if previous_index is None:
		os.environ.pop("DEVLOGS_INDEX", None)
	else:
		os.environ["DEVLOGS_INDEX"] = previous_index
	if opensearch_client.indices.exists(index=index_name):
		opensearch_client.indices.delete(index=index_name)
	if legacy_template_created:
		try:
			opensearch_client.indices.delete_template(name="devlogs-logs-template")
		except Exception:
			pass

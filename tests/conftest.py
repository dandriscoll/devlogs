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
from devlogs.opensearch.mappings import (
	build_log_index_template,
	build_legacy_log_template,
	get_template_names,
)


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
	composable_template_created = False
	index_name = f"devlogs-logs-test-{uuid.uuid4().hex}"
	template_body = build_log_index_template(index_name)
	legacy_body = build_legacy_log_template(index_name)
	template_name, legacy_template_name = get_template_names(index_name)
	try:
		opensearch_client.indices.delete_index_template(name=template_name)
	except Exception:
		pass
	try:
		opensearch_client.indices.delete_template(name=legacy_template_name)
	except Exception:
		pass
	try:
		opensearch_client.indices.put_index_template(
			name=template_name,
			body=template_body,
		)
		composable_template_created = True
	except Exception:
		opensearch_client.indices.put_template(
			name=legacy_template_name,
			body=legacy_body,
		)
		legacy_template_created = True
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
	if composable_template_created:
		try:
			opensearch_client.indices.delete_index_template(name=template_name)
		except Exception:
			pass
	if legacy_template_created:
		try:
			opensearch_client.indices.delete_template(name=legacy_template_name)
		except Exception:
			pass

import logging

from devlogs.context import operation
from devlogs.handler import DiagnosticsHandler
from devlogs.rollup import rollup_operation, rollup_operations


def _get_logger(name, handler):
	logger = logging.getLogger(name)
	logger.handlers = [handler]
	logger.setLevel(logging.DEBUG)
	logger.propagate = False
	return logger


def _count_children(client, index, operation_id):
	resp = client.search(
		index=index,
		body={
			"query": {
				"bool": {
					"filter": [
						{"term": {"doc_type": "log_entry"}},
						{"term": {"operation_id": operation_id}},
					]
				}
			}
		},
	)
	return len(resp.get("hits", {}).get("hits", []))


def _get_parent_doc(client, index, operation_id):
	resp = client.search(
		index=index,
		body={
			"query": {
				"bool": {
					"filter": [
						{"term": {"doc_type": "operation"}},
						{"term": {"operation_id": operation_id}},
					]
				}
			}
		},
	)
	hits = resp.get("hits", {}).get("hits", [])
	return hits[0]["_source"] if hits else None


def test_rollup_operation_creates_parent_and_deletes_children(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	handler.setFormatter(logging.Formatter("%(message)s"))
	logger = _get_logger("rollup-one", handler)

	with operation(operation_id="op-rollup", area="api", rollup=False):
		logger.info("first message")
		logger.error("second message")

	opensearch_client.indices.refresh(index=test_index)
	assert _count_children(opensearch_client, test_index, "op-rollup") == 2

	assert rollup_operation(opensearch_client, test_index, "op-rollup") is True
	opensearch_client.indices.refresh(index=test_index)

	parent = _get_parent_doc(opensearch_client, test_index, "op-rollup")
	assert parent is not None
	assert parent["doc_type"] == "operation"
	assert parent["area"] == "api"
	assert parent["counts_by_level"].get("INFO") == 1
	assert parent["counts_by_level"].get("ERROR") == 1
	assert parent["error_count"] == 1
	assert "first message" in (parent.get("message") or "")
	assert "second message" in (parent.get("message") or "")

	assert _count_children(opensearch_client, test_index, "op-rollup") == 0


def test_rollup_operations_handles_multiple_operations(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	handler.setFormatter(logging.Formatter("%(message)s"))
	logger = _get_logger("rollup-many", handler)

	with operation(operation_id="op-a", area="jobs", rollup=False):
		logger.info("alpha")
	with operation(operation_id="op-b", area="web", rollup=False):
		logger.info("beta")

	opensearch_client.indices.refresh(index=test_index)
	assert _count_children(opensearch_client, test_index, "op-a") == 1
	assert _count_children(opensearch_client, test_index, "op-b") == 1

	rollup_operations(opensearch_client, test_index)
	opensearch_client.indices.refresh(index=test_index)

	parent_a = _get_parent_doc(opensearch_client, test_index, "op-a")
	parent_b = _get_parent_doc(opensearch_client, test_index, "op-b")
	assert parent_a is not None
	assert parent_b is not None
	assert "alpha" in (parent_a.get("message") or "")
	assert "beta" in (parent_b.get("message") or "")

	assert _count_children(opensearch_client, test_index, "op-a") == 0
	assert _count_children(opensearch_client, test_index, "op-b") == 0

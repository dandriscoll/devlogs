import logging
import time

from devlogs.context import operation
from devlogs.handler import DiagnosticsHandler, OpenSearchHandler
from devlogs.opensearch.queries import search_logs, tail_logs


def _get_logger(name, handler):
	logger = logging.getLogger(name)
	logger.handlers = [handler]
	logger.setLevel(logging.DEBUG)
	logger.propagate = False
	return logger


def test_diagnostics_handler_child_with_context(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-child", handler)

	with operation(operation_id="op-1", area="web"):
		logger.info("child log")

	opensearch_client.indices.refresh(index=test_index)
	results = search_logs(opensearch_client, test_index, operation_id="op-1")
	assert results
	doc = results[0]
	assert doc["doc_type"]["name"] == "log_entry"
	assert doc["doc_type"]["parent"] == "op-1"
	assert doc["area"] == "web"


def test_diagnostics_handler_parent_without_context(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-parent", handler)

	logger.warning("parent log")

	opensearch_client.indices.refresh(index=test_index)
	resp = opensearch_client.search(
		index=test_index,
		body={"query": {"term": {"doc_type": "operation"}}},
	)
	hits = resp.get("hits", {}).get("hits", [])
	assert hits
	doc = hits[0]["_source"]
	assert doc["doc_type"] == "operation"


def test_diagnostics_handler_extra_context_child(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-extra", handler)

	logger.info("extra context", extra={"operation_id": "op-extra", "area": "jobs"})

	opensearch_client.indices.refresh(index=test_index)
	results = search_logs(opensearch_client, test_index, operation_id="op-extra")
	assert results
	doc = results[0]
	assert doc["doc_type"]["name"] == "log_entry"
	assert doc["doc_type"]["parent"] == "op-extra"
	assert doc["area"] == "jobs"


def test_index_and_query_varied_contexts(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-query", handler)

	long_area = "a" * 64
	long_operation = "op-" + ("x" * 120)

	with operation(operation_id="op-short", area="a"):
		logger.info("alpha one")
	with operation(operation_id="op-medium", area="service-api"):
		logger.info("beta two")
	with operation(operation_id=long_operation, area=long_area):
		logger.info("gamma three")

	opensearch_client.indices.refresh(index=test_index)
	results = search_logs(opensearch_client, test_index, area="service-api")
	assert len(results) == 1
	assert results[0]["message"] == "beta two"

	results = search_logs(opensearch_client, test_index, operation_id=long_operation)
	assert len(results) == 1
	assert results[0]["area"] == long_area


def test_nested_contexts_are_distinct(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-nested", handler)

	with operation(operation_id="outer", area="api"):
		logger.info("outer start")
		with operation(operation_id="inner", area="jobs"):
			logger.info("inner")
		logger.info("outer end")

	opensearch_client.indices.refresh(index=test_index)
	results = search_logs(opensearch_client, test_index, operation_id="outer")
	assert len(results) == 2
	results = search_logs(opensearch_client, test_index, operation_id="inner")
	assert len(results) == 1


def test_tail_logs_pagination(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-tail", handler)

	with operation(operation_id="op-tail", area="web"):
		for i in range(5):
			logger.info(f"msg {i}")
			time.sleep(0.001)

	opensearch_client.indices.refresh(index=test_index)
	page1, cursor = tail_logs(
		opensearch_client,
		test_index,
		operation_id="op-tail",
		limit=2,
	)
	page2, cursor2 = tail_logs(
		opensearch_client,
		test_index,
		operation_id="op-tail",
		limit=2,
		search_after=cursor,
	)
	page3, _ = tail_logs(
		opensearch_client,
		test_index,
		operation_id="op-tail",
		limit=2,
		search_after=cursor2,
	)

	messages = [doc["message"] for doc in page1 + page2 + page3]
	assert messages[:5] == [f"msg {i}" for i in range(5)]


def test_tail_logs_finds_opensearch_handler_entries(opensearch_client, test_index):
	handler = OpenSearchHandler(opensearch_client=opensearch_client, index_name=test_index)
	handler.setFormatter(logging.Formatter("%(message)s"))
	logger = _get_logger("devlogs-tail-basic", handler)

	with operation(operation_id="op-basic", area="web"):
		logger.info("basic message")

	opensearch_client.indices.refresh(index=test_index)
	results, _ = tail_logs(opensearch_client, test_index, operation_id="op-basic", limit=5)
	assert any(doc["message"] == "basic message" for doc in results)

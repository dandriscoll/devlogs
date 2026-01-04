import logging
import time

from devlogs.context import operation
from devlogs.handler import DiagnosticsHandler, OpenSearchHandler
from devlogs.opensearch.queries import normalize_log_entries, search_logs, tail_logs


def _get_logger(name, handler):
	logger = logging.getLogger(name)
	logger.handlers = [handler]
	logger.setLevel(logging.DEBUG)
	logger.propagate = False
	return logger


def test_diagnostics_handler_with_context(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-context", handler)

	with operation(operation_id="op-1", area="web"):
		logger.info("context log")

	opensearch_client.indices.refresh(index=test_index)
	results = search_logs(opensearch_client, test_index, operation_id="op-1")
	assert results
	doc = results[0]
	assert doc["doc_type"] == "log_entry"
	assert doc["area"] == "web"
	assert "context log" in (doc.get("message") or "")


def test_diagnostics_handler_without_context(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-basic", handler)

	logger.warning("basic log")

	opensearch_client.indices.refresh(index=test_index)
	resp = opensearch_client.search(
		index=test_index,
		body={"query": {"term": {"doc_type": "log_entry"}}},
	)
	hits = resp.get("hits", {}).get("hits", [])
	assert hits
	doc = hits[0]["_source"]
	assert doc["doc_type"] == "log_entry"


def test_diagnostics_handler_extra_context(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-extra", handler)

	logger.info("extra context", extra={"operation_id": "op-extra", "area": "jobs"})

	opensearch_client.indices.refresh(index=test_index)
	results = search_logs(opensearch_client, test_index, operation_id="op-extra")
	assert results
	doc = results[0]
	assert doc["doc_type"] == "log_entry"
	assert doc["operation_id"] == "op-extra"
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
	assert "beta two" in (results[0].get("message") or "")

	results = search_logs(opensearch_client, test_index, operation_id=long_operation)
	assert len(results) == 1
	assert results[0]["area"] == long_area
	assert "gamma three" in (results[0].get("message") or "")


def test_nested_contexts_are_distinct(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-nested", handler)

	with operation(operation_id="outer", area="api"):
		logger.info("outer start")
		with operation(operation_id="inner", area="jobs"):
			logger.info("inner")
		logger.info("outer end")

	opensearch_client.indices.refresh(index=test_index)
	# With flat documents, we get 2 separate log entries for outer
	outer_results = search_logs(opensearch_client, test_index, operation_id="outer")
	assert len(outer_results) == 2
	outer_entries = normalize_log_entries(outer_results)
	assert any("outer start" in (entry.get("message") or "") for entry in outer_entries)
	assert any("outer end" in (entry.get("message") or "") for entry in outer_entries)

	# Inner operation has its own log entry
	inner_results = search_logs(opensearch_client, test_index, operation_id="inner")
	assert len(inner_results) == 1
	inner_entry = normalize_log_entries(inner_results)[0]
	assert inner_entry.get("operation_id") == "inner"
	assert inner_entry.get("area") == "jobs"
	assert "inner" in (inner_entry.get("message") or "")


def test_tail_logs_follow_returns_new_entries(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-tail", handler)

	with operation(operation_id="op-tail", area="web"):
		for i in range(3):
			logger.info(f"msg {i}")
			time.sleep(0.001)

	opensearch_client.indices.refresh(index=test_index)
	page1, cursor = tail_logs(
		opensearch_client,
		test_index,
		operation_id="op-tail",
		limit=2,
	)
	entries1 = normalize_log_entries(page1)
	assert [entry.get("message") for entry in entries1] == ["msg 1", "msg 2"]

	with operation(operation_id="op-tail", area="web"):
		for i in range(3, 5):
			logger.info(f"msg {i}")
			time.sleep(0.001)

	opensearch_client.indices.refresh(index=test_index)
	page2, _ = tail_logs(
		opensearch_client,
		test_index,
		operation_id="op-tail",
		limit=5,
		search_after=cursor,
	)
	entries2 = normalize_log_entries(page2)
	assert [entry.get("message") for entry in entries2] == ["msg 3", "msg 4"]


def test_tail_logs_finds_opensearch_handler_entries(opensearch_client, test_index):
	handler = OpenSearchHandler(opensearch_client=opensearch_client, index_name=test_index)
	handler.setFormatter(logging.Formatter("%(message)s"))
	logger = _get_logger("devlogs-tail-basic", handler)

	with operation(operation_id="op-basic", area="web"):
		logger.info("basic message")

	opensearch_client.indices.refresh(index=test_index)
	results, _ = tail_logs(opensearch_client, test_index, operation_id="op-basic", limit=5)
	assert any("basic message" in (doc.get("message") or "") for doc in results)


def test_features_are_indexed_and_normalized(opensearch_client, test_index):
	handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
	logger = _get_logger("devlogs-features", handler)

	with operation(operation_id="op-features", area="api"):
		logger.info(
			"feature log",
			extra={"features": {"user": "alice", "plan": "pro", "count": 3}},
		)

	opensearch_client.indices.refresh(index=test_index)
	results = search_logs(opensearch_client, test_index, operation_id="op-features")
	assert results
	entries = normalize_log_entries(results)
	assert any(
		entry.get("features", {}).get("user") == "alice"
		and entry.get("features", {}).get("plan") == "pro"
		and entry.get("features", {}).get("count") == 3
		for entry in entries
	)

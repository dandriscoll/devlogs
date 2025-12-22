import logging
import time

from devlogs.context import operation
from devlogs.handler import DiagnosticsHandler
from devlogs.opensearch.queries import search_logs, tail_logs


class FakeOpenSearch:
	def __init__(self):
		self._docs = []
		self._counter = 0

	def index(self, index, body, routing=None, id=None, refresh=None):
		self._counter += 1
		doc_id = id or f"doc-{self._counter}"
		self._docs.append(
			{"_id": doc_id, "_index": index, "_source": body, "_routing": routing}
		)
		return {"_id": doc_id}

	def search(self, index, body):
		hits = [doc for doc in self._docs if doc["_index"] == index]
		query = body.get("query", {})
		hits = _apply_query(hits, query)
		sort = body.get("sort", [])
		search_after = body.get("search_after")
		hits = _apply_sort_and_after(hits, sort, search_after)
		size = body.get("size", len(hits))
		return {"hits": {"hits": hits[:size]}}


def _apply_query(hits, query):
	bool_query = query.get("bool", {}) if isinstance(query, dict) else {}
	filters = bool_query.get("filter", [])
	must = bool_query.get("must", [])
	for item in filters:
		if "term" in item:
			field, value = next(iter(item["term"].items()))
			def matches_term(doc):
				actual = doc["_source"].get(field)
				if field == "doc_type" and isinstance(actual, dict):
					return actual.get("name") == value
				return actual == value
			hits = [doc for doc in hits if matches_term(doc)]
		elif "range" in item and "timestamp" in item["range"]:
			gte = item["range"]["timestamp"].get("gte")
			if gte is not None:
				hits = [doc for doc in hits if doc["_source"].get("timestamp") >= gte]
	for item in must:
		if "simple_query_string" in item:
			query_text = item["simple_query_string"].get("query", "")
			terms = [t for t in query_text.split() if t]
			def matches(doc):
				fields = [
					doc["_source"].get("message", ""),
					doc["_source"].get("logger_name", ""),
					doc["_source"].get("operation_id", ""),
					doc["_source"].get("area", ""),
				]
				blob = " ".join(fields).lower()
				return all(term.lower() in blob for term in terms)
			hits = [doc for doc in hits if matches(doc)]
	return hits


def _apply_sort_and_after(hits, sort, search_after):
	def sort_key(doc):
		timestamp = doc["_source"].get("timestamp", 0)
		return (timestamp, doc["_id"])

	reverse = False
	if sort:
		sort_field = next(iter(sort[0].items()))
		reverse = sort_field[1] == "desc"

	hits = sorted(hits, key=sort_key, reverse=reverse)

	if search_after:
		after_key = (search_after[0], search_after[1])
		if reverse:
			hits = [doc for doc in hits if sort_key(doc) < after_key]
		else:
			hits = [doc for doc in hits if sort_key(doc) > after_key]

	scored = []
	for doc in hits:
		key = sort_key(doc)
		doc = dict(doc)
		doc["sort"] = [key[0], key[1]]
		scored.append(doc)
	return scored


def _get_logger(name, handler):
	logger = logging.getLogger(name)
	logger.handlers = [handler]
	logger.setLevel(logging.DEBUG)
	logger.propagate = False
	return logger


def test_diagnostics_handler_child_with_context():
	client = FakeOpenSearch()
	handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
	logger = _get_logger("devlogs-child", handler)

	with operation(operation_id="op-1", area="web"):
		logger.info("child log")

	assert client._docs
	doc = client._docs[0]
	assert doc["_source"]["doc_type"]["name"] == "log_entry"
	assert doc["_source"]["doc_type"]["parent"] == "op-1"
	assert doc["_routing"] == "op-1"
	assert doc["_source"]["area"] == "web"


def test_diagnostics_handler_parent_without_context():
	client = FakeOpenSearch()
	handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
	logger = _get_logger("devlogs-parent", handler)

	logger.warning("parent log")

	doc = client._docs[0]
	assert doc["_source"]["doc_type"] == "operation"
	assert doc["_routing"] == doc["_source"]["operation_id"]


def test_diagnostics_handler_extra_context_child():
	client = FakeOpenSearch()
	handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
	logger = _get_logger("devlogs-extra", handler)

	logger.info("extra context", extra={"operation_id": "op-extra", "area": "jobs"})

	doc = client._docs[0]
	assert doc["_source"]["doc_type"]["name"] == "log_entry"
	assert doc["_source"]["doc_type"]["parent"] == "op-extra"
	assert doc["_source"]["area"] == "jobs"


def test_index_and_query_varied_contexts():
	client = FakeOpenSearch()
	handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
	logger = _get_logger("devlogs-query", handler)

	long_area = "a" * 64
	long_operation = "op-" + ("x" * 120)

	with operation(operation_id="op-short", area="a"):
		logger.info("alpha one")
	with operation(operation_id="op-medium", area="service-api"):
		logger.info("beta two")
	with operation(operation_id=long_operation, area=long_area):
		logger.info("gamma three")

	results = search_logs(client, "devlogs-logs-0001", area="service-api")
	assert len(results) == 1
	assert results[0]["message"] == "beta two"

	results = search_logs(client, "devlogs-logs-0001", operation_id=long_operation)
	assert len(results) == 1
	assert results[0]["area"] == long_area


def test_nested_contexts_are_distinct():
	client = FakeOpenSearch()
	handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
	logger = _get_logger("devlogs-nested", handler)

	with operation(operation_id="outer", area="api"):
		logger.info("outer start")
		with operation(operation_id="inner", area="jobs"):
			logger.info("inner")
		logger.info("outer end")

	results = search_logs(client, "devlogs-logs-0001", operation_id="outer")
	assert len(results) == 2
	results = search_logs(client, "devlogs-logs-0001", operation_id="inner")
	assert len(results) == 1


def test_tail_logs_pagination():
	client = FakeOpenSearch()
	handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
	logger = _get_logger("devlogs-tail", handler)

	with operation(operation_id="op-tail", area="web"):
		for i in range(5):
			logger.info(f"msg {i}")
			time.sleep(0.001)

	page1, cursor = tail_logs(
		client,
		"devlogs-logs-0001",
		operation_id="op-tail",
		limit=2,
	)
	page2, cursor2 = tail_logs(
		client,
		"devlogs-logs-0001",
		operation_id="op-tail",
		limit=2,
		search_after=cursor,
	)
	page3, _ = tail_logs(
		client,
		"devlogs-logs-0001",
		operation_id="op-tail",
		limit=2,
		search_after=cursor2,
	)

	messages = [doc["message"] for doc in page1 + page2 + page3]
	assert messages[:5] == [f"msg {i}" for i in range(5)]

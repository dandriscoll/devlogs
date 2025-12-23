import logging
import pytest
from devlogs import context
from devlogs.handler import DiagnosticsHandler

def test_operation_context_sets_and_resets():
    with context.operation("opid", "web"):
        assert context.get_operation_id() == "opid"
        assert context.get_area() == "web"
    assert context.get_operation_id() is None
    assert context.get_area() is None

def test_set_area():
    context.set_area("jobs")
    assert context.get_area() == "jobs"


class DummyClient:
    def __init__(self):
        self.indexed = []

    def index(self, index, body, routing=None, id=None, refresh=None):
        self.indexed.append({"index": index, "body": body, "routing": routing})


def _get_logger(name, handler):
    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


def test_diagnostics_handler_uses_context_for_child_docs():
    client = DummyClient()
    handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
    logger = _get_logger("ctx-child", handler)

    with context.operation("op-ctx", "web"):
        logger.info("hello")

    assert client.indexed
    doc = client.indexed[0]["body"]
    assert doc["doc_type"]["name"] == "log_entry"
    assert doc["doc_type"]["parent"] == "op-ctx"
    assert doc["area"] == "web"
    assert client.indexed[0]["routing"] == "op-ctx"


def test_diagnostics_handler_nested_contexts():
    client = DummyClient()
    handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
    logger = _get_logger("ctx-nested", handler)

    with context.operation("outer", "api"):
        logger.info("outer")
        with context.operation("inner", "jobs"):
            logger.info("inner")
        logger.info("outer-two")

    outer_docs = [d for d in client.indexed if d["body"]["operation_id"] == "outer"]
    inner_docs = [d for d in client.indexed if d["body"]["operation_id"] == "inner"]
    assert len(outer_docs) == 2
    assert len(inner_docs) == 1
    assert outer_docs[0]["body"]["area"] == "api"
    assert inner_docs[0]["body"]["area"] == "jobs"


def test_diagnostics_handler_extra_overrides_context():
    client = DummyClient()
    handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-logs-0001")
    logger = _get_logger("ctx-extra", handler)

    with context.operation("op-context", "web"):
        logger.info("override", extra={"operation_id": "op-extra", "area": "jobs"})

    doc = client.indexed[0]["body"]
    assert doc["doc_type"]["name"] == "log_entry"
    assert doc["doc_type"]["parent"] == "op-extra"
    assert doc["area"] == "jobs"

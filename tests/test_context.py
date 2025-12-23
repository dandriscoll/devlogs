import logging
import pytest
from devlogs import context
from devlogs.handler import DiagnosticsHandler
from devlogs.opensearch.queries import search_logs

def test_operation_context_sets_and_resets():
    with context.operation("opid", "web"):
        assert context.get_operation_id() == "opid"
        assert context.get_area() == "web"
    assert context.get_operation_id() is None
    assert context.get_area() is None

def test_set_area():
    context.set_area("jobs")
    assert context.get_area() == "jobs"


def _get_logger(name, handler):
    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


def test_diagnostics_handler_uses_context_for_child_docs(opensearch_client, test_index):
    handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
    logger = _get_logger("ctx-child", handler)

    with context.operation("op-ctx", "web"):
        logger.info("hello")

    opensearch_client.indices.refresh(index=test_index)
    results = search_logs(opensearch_client, test_index, operation_id="op-ctx")
    assert results
    doc = results[0]
    assert doc["doc_type"]["name"] == "log_entry"
    assert doc["doc_type"]["parent"] == "op-ctx"
    assert doc["area"] == "web"


def test_diagnostics_handler_nested_contexts(opensearch_client, test_index):
    handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
    logger = _get_logger("ctx-nested", handler)

    with context.operation("outer", "api"):
        logger.info("outer")
        with context.operation("inner", "jobs"):
            logger.info("inner")
        logger.info("outer-two")

    opensearch_client.indices.refresh(index=test_index)
    outer_docs = search_logs(opensearch_client, test_index, operation_id="outer")
    inner_docs = search_logs(opensearch_client, test_index, operation_id="inner")
    assert len(outer_docs) == 2
    assert len(inner_docs) == 1
    assert outer_docs[0]["area"] == "api"
    assert inner_docs[0]["area"] == "jobs"


def test_diagnostics_handler_extra_overrides_context(opensearch_client, test_index):
    handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
    logger = _get_logger("ctx-extra", handler)

    with context.operation("op-context", "web"):
        logger.info("override", extra={"operation_id": "op-extra", "area": "jobs"})

    opensearch_client.indices.refresh(index=test_index)
    results = search_logs(opensearch_client, test_index, operation_id="op-extra")
    doc = results[0]
    assert doc["doc_type"]["name"] == "log_entry"
    assert doc["doc_type"]["parent"] == "op-extra"
    assert doc["area"] == "jobs"

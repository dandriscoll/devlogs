import logging

from devlogs.context import operation
from devlogs.handler import DiagnosticsHandler


def test_handler_emits_and_indexes(opensearch_client, test_index):
    handler = DiagnosticsHandler(opensearch_client=opensearch_client, index_name=test_index)
    logger = logging.getLogger("devlogs-test")
    logger.setLevel(logging.DEBUG)
    logger.handlers = [handler]
    logger.propagate = False
    with operation("op-test", "web"):
        logger.debug("hello world")
    opensearch_client.indices.refresh(index=test_index)
    resp = opensearch_client.search(
        index=test_index,
        body={"query": {"term": {"operation_id": "op-test"}}},
    )
    hits = resp.get("hits", {}).get("hits", [])
    assert hits

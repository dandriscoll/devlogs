"""Tests for OpenSearch query helpers."""

from unittest.mock import patch

from devlogs.opensearch.queries import (
    get_error_context,
    get_last_errors,
    get_operation_logs,
    list_error_signatures,
    list_recent_operations,
    search_logs_page,
)


class DummyClient:
    """Minimal client for query helper tests."""

    def __init__(self, response):
        self.response = response
        self.last_call = None

    def search(self, index, body):
        self.last_call = {"index": index, "body": body}
        return self.response


def test_search_logs_page_uses_cursor_and_sort():
    response = {
        "hits": {
            "hits": [
                {
                    "_source": {"message": "test"},
                    "_id": "doc-1",
                    "sort": ["2025-12-26T10:00:00Z", "doc-1"],
                }
            ]
        }
    }
    client = DummyClient(response)
    docs, cursor = search_logs_page(
        client,
        "index",
        query="boom",
        since="2025-12-26T00:00:00Z",
        until="2025-12-26T23:59:59Z",
        limit=1,
        cursor=["2025-12-25T23:59:59Z", "doc-0"],
        sort_order="asc",
    )

    body = client.last_call["body"]
    assert body["search_after"] == ["2025-12-25T23:59:59Z", "doc-0"]
    assert body["sort"][0]["timestamp"] == "asc"
    assert docs[0]["id"] == "doc-1"
    assert cursor == ["2025-12-26T10:00:00Z", "doc-1"]


def test_list_recent_operations_orders_and_includes_last_error():
    response = {
        "aggregations": {
            "by_operation": {
                "buckets": [
                    {
                        "key": "op-123",
                        "doc_count": 4,
                        "area": {"buckets": [{"key": "api"}]},
                        "time_range": {
                            "min": 1.0,
                            "max": 3.0,
                            "min_as_string": "2025-12-26T10:00:00Z",
                            "max_as_string": "2025-12-26T10:00:02Z",
                        },
                        "by_level": {"buckets": [{"key": "error", "doc_count": 1}]},
                        "error_count": {"doc_count": 1},
                        "last_activity": {"value_as_string": "2025-12-26T10:00:02Z"},
                        "last_error": {
                            "last_error_hit": {
                                "hits": {
                                    "hits": [
                                        {
                                            "_source": {
                                                "timestamp": "2025-12-26T10:00:02Z",
                                                "level": "error",
                                                "message": "boom",
                                                "operation_id": "op-123",
                                            }
                                        }
                                    ]
                                }
                            }
                        },
                    }
                ]
            }
        }
    }
    client = DummyClient(response)
    operations = list_recent_operations(
        client,
        "index",
        order_by="error_count",
        limit=5,
    )

    body = client.last_call["body"]
    assert body["aggs"]["by_operation"]["terms"]["order"] == {"error_count": "desc"}
    assert operations[0]["operation_id"] == "op-123"
    assert operations[0]["last_error"]["message"] == "boom"
    assert operations[0]["duration_ms"] == 2


def test_list_error_signatures_builds_filters_and_field():
    response = {
        "aggregations": {
            "by_signature": {
                "buckets": [
                    {
                        "key": "Traceback",
                        "doc_count": 2,
                        "last_seen": {"value_as_string": "2025-12-26T10:00:00Z"},
                        "sample": {
                            "hits": {
                                "hits": [
                                    {
                                        "_source": {
                                            "message": "error",
                                            "exception": "Traceback",
                                        }
                                    }
                                ]
                            }
                        },
                    }
                ]
            }
        }
    }
    client = DummyClient(response)
    signatures = list_error_signatures(client, "index", field="exception")

    body = client.last_call["body"]
    filters = body["query"]["bool"]["filter"]
    assert {"terms": {"level": ["error", "critical"]}} in filters
    assert {"exists": {"field": "exception"}} in filters
    assert body["aggs"]["by_signature"]["terms"]["field"] == "exception.keyword"
    assert signatures[0]["signature"] == "Traceback"


def test_list_error_signatures_allows_missing_and_custom_field():
    response = {"aggregations": {"by_signature": {"buckets": []}}}
    client = DummyClient(response)
    list_error_signatures(
        client,
        "index",
        field="message.keyword",
        include_missing=True,
    )

    body = client.last_call["body"]
    filters = body["query"]["bool"]["filter"]
    assert {"exists": {"field": "message.keyword"}} not in filters
    assert body["aggs"]["by_signature"]["terms"]["field"] == "message.keyword"


def test_get_last_errors_filters_and_sorts():
    response = {
        "hits": {
            "hits": [
                {
                    "_source": {"message": "boom", "level": "error"},
                    "_id": "doc-1",
                }
            ]
        }
    }
    client = DummyClient(response)
    results = get_last_errors(
        client,
        "index",
        area="api",
        limit=1,
    )

    body = client.last_call["body"]
    filters = body["query"]["bool"]["filter"]
    assert {"terms": {"level": ["error", "critical"]}} in filters
    assert body["sort"][0]["timestamp"] == "desc"
    assert results[0]["message"] == "boom"


def test_get_error_context_orders_entries():
    before_docs = [
        {"id": "doc-2", "sort": [2]},
        {"id": "doc-1", "sort": [1]},
    ]
    after_docs = [{"id": "doc-3", "sort": [3]}]

    with patch("devlogs.opensearch.queries.search_logs_page") as mock_search:
        mock_search.side_effect = [(before_docs, None), (after_docs, None)]
        results = get_error_context(
            client="client",
            index="index",
            anchor_timestamp="2025-12-26T10:00:00Z",
            before=1,
            after=1,
        )

    assert [doc["id"] for doc in results] == ["doc-1", "doc-2", "doc-3"]


def test_get_operation_logs_uses_chronological_sort():
    with patch("devlogs.opensearch.queries.search_logs_page") as mock_search:
        mock_search.return_value = ([{"id": "doc-1"}], ["cursor"])
        docs, cursor = get_operation_logs(
            client="client",
            index="index",
            operation_id="op-1",
        )

    assert docs == [{"id": "doc-1"}]
    assert cursor == ["cursor"]
    _, kwargs = mock_search.call_args
    assert kwargs["sort_order"] == "asc"

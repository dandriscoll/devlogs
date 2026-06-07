"""Integration tests for application/component aggregation and filtering.

These exercise the real OpenSearch runtime (the layer where the bug lived: a
`terms` aggregation on a `text`-mapped field throws, and a bare `term` filter on
a `text` field fails to match multi-token values). Mock-based unit tests cannot
catch either, which is why `devlogs applications` shipped broken.

Two index generations are covered:
  * legacy  -> application/component dynamically mapped as `text` (+ `.keyword`),
               as on every index created before the template carried them.
  * current -> application/component mapped as `keyword` by the template.

The query layer must work on both via the single `<field>.keyword` path.
"""

import uuid

import pytest

from devlogs.opensearch.queries import list_applications, search_logs

pytestmark = pytest.mark.integration


_DOCS = [
    {"doc_type": "log_entry", "timestamp": "2026-06-01T00:00:00Z", "level": "info",
     "application": "my-app", "component": "web-frontend", "area": "x",
     "operation_id": "o1", "message": "alpha"},
    {"doc_type": "log_entry", "timestamp": "2026-06-01T00:01:00Z", "level": "error",
     "application": "my-app", "component": "web-frontend", "area": "x",
     "operation_id": "o1", "message": "beta"},
    {"doc_type": "log_entry", "timestamp": "2026-06-01T00:02:00Z", "level": "info",
     "application": "other-svc", "component": "api", "area": "y",
     "operation_id": "o2", "message": "gamma"},
]


def _seed(client, index, docs=_DOCS):
    for doc in docs:
        client.index(index=index, body=doc)
    client.indices.refresh(index=index)


@pytest.fixture()
def legacy_text_index(opensearch_client):
    """An index with NO explicit application/component mapping, so OpenSearch
    dynamically maps them as `text` (+ auto `.keyword`) — i.e. a pre-fix index."""
    index_name = f"devlogs-legacy-test-{uuid.uuid4().hex}"
    opensearch_client.indices.create(index=index_name)
    try:
        yield index_name
    finally:
        if opensearch_client.indices.exists(index=index_name):
            opensearch_client.indices.delete(index=index_name)


def test_list_applications_on_legacy_text_index(opensearch_client, legacy_text_index):
    # Reproduce-first regression: before the `.keyword` fix this returned [] (the
    # aggregation threw and was swallowed) -> "No applications found."
    _seed(opensearch_client, legacy_text_index)
    mapping = opensearch_client.indices.get_mapping(index=legacy_text_index)
    props = mapping[legacy_text_index]["mappings"]["properties"]
    assert props["application"]["type"] == "text"  # confirm we're testing the legacy shape

    apps = list_applications(client=opensearch_client, index=legacy_text_index)
    by_name = {a["application"]: a for a in apps}
    assert set(by_name) == {"my-app", "other-svc"}
    assert by_name["my-app"]["log_count"] == 2
    assert by_name["my-app"]["error_count"] == 1


def test_multitoken_filter_on_legacy_text_index(opensearch_client, legacy_text_index):
    # A bare `term` on a text field fails to match multi-token values like
    # "my-app" (tokenized to ["my","app"]). The `.keyword` filter matches.
    _seed(opensearch_client, legacy_text_index)
    results = search_logs(client=opensearch_client, index=legacy_text_index, application="my-app")
    assert len(results) == 2
    results = search_logs(client=opensearch_client, index=legacy_text_index,
                          application="my-app", component="web-frontend")
    assert len(results) == 2


def test_list_applications_on_current_template_index(opensearch_client, test_index):
    # test_index applies build_log_index_template -> keyword mapping.
    mapping = opensearch_client.indices.get_mapping(index=test_index)
    props = mapping[test_index]["mappings"]["properties"]
    assert props["application"]["type"] == "keyword"
    assert props["application"]["fields"]["keyword"]["type"] == "keyword"

    _seed(opensearch_client, test_index)
    apps = list_applications(client=opensearch_client, index=test_index)
    by_name = {a["application"]: a for a in apps}
    assert set(by_name) == {"my-app", "other-svc"}
    assert by_name["my-app"]["log_count"] == 2

    # component filter narrows the aggregation
    apps = list_applications(client=opensearch_client, index=test_index, component="api")
    assert {a["application"] for a in apps} == {"other-svc"}

    # multi-token filter works on the new mapping too
    results = search_logs(client=opensearch_client, index=test_index, application="my-app")
    assert len(results) == 2

"""Tests for Loki query helpers."""

import json
from unittest.mock import patch, MagicMock

from devlogs.loki.queries import (
    build_stream_selector,
    list_applications,
    list_areas,
    list_operations,
)


def _mock_loki_get(response):
    """Return a patcher for _loki_get that captures calls."""
    mock = MagicMock(return_value=response)
    return patch("devlogs.loki.queries._loki_get", mock), mock


class TestListApplications:
    def test_returns_sorted_application_names(self):
        patcher, mock = _mock_loki_get({"data": ["zebra-app", "alpha-app", "mid-app"]})
        with patcher:
            result = list_applications("http://loki:3100")
        assert result == [
            {"application": "alpha-app"},
            {"application": "mid-app"},
            {"application": "zebra-app"},
        ]
        mock.assert_called_once()
        args = mock.call_args
        assert args[0][1] == "/loki/api/v1/label/application/values"

    def test_passes_time_params_when_since_given(self):
        patcher, mock = _mock_loki_get({"data": ["app1"]})
        with patcher:
            result = list_applications("http://loki:3100", since="1h")
        params = mock.call_args[0][2]
        assert "start" in params
        assert "end" in params

    def test_returns_empty_list_when_no_data(self):
        patcher, mock = _mock_loki_get({"data": []})
        with patcher:
            result = list_applications("http://loki:3100")
        assert result == []

    def test_passes_token(self):
        patcher, mock = _mock_loki_get({"data": []})
        with patcher:
            list_applications("http://loki:3100", token="my-token")
        assert mock.call_args[1]["token"] == "my-token"


class TestListAreas:
    def test_returns_sorted_area_names(self):
        patcher, mock = _mock_loki_get({"data": ["payments", "auth", "billing"]})
        with patcher:
            result = list_areas("http://loki:3100")
        assert result == [
            {"area": "auth"},
            {"area": "billing"},
            {"area": "payments"},
        ]
        args = mock.call_args
        assert args[0][1] == "/loki/api/v1/label/area/values"

    def test_passes_match_selector_for_application(self):
        patcher, mock = _mock_loki_get({"data": ["area1"]})
        with patcher:
            list_areas("http://loki:3100", application="myapp")
        params = mock.call_args[0][2]
        assert "match[]" in params
        assert "myapp" in params["match[]"]

    def test_no_match_selector_without_application(self):
        patcher, mock = _mock_loki_get({"data": []})
        with patcher:
            list_areas("http://loki:3100")
        params = mock.call_args[0][2]
        assert "match[]" not in params


class TestListOperations:
    def test_extracts_distinct_operation_ids(self):
        streams_response = {
            "data": {
                "resultType": "streams",
                "result": [
                    {
                        "stream": {"application": "myapp"},
                        "values": [
                            ["1000000000", json.dumps({"operation_id": "op-1", "message": "hello"})],
                            ["1000000001", json.dumps({"operation_id": "op-2", "message": "world"})],
                            ["1000000002", json.dumps({"operation_id": "op-1", "message": "again"})],
                        ],
                    }
                ],
            }
        }
        patcher, mock = _mock_loki_get(streams_response)
        with patcher:
            result = list_operations("http://loki:3100", application="myapp")
        assert len(result) == 2
        op_ids = {r["operation_id"] for r in result}
        assert op_ids == {"op-1", "op-2"}

    def test_respects_limit(self):
        entries = [
            ["100000000" + str(i), json.dumps({"operation_id": f"op-{i}", "message": "m"})]
            for i in range(20)
        ]
        streams_response = {
            "data": {
                "resultType": "streams",
                "result": [{"stream": {}, "values": entries}],
            }
        }
        patcher, mock = _mock_loki_get(streams_response)
        with patcher:
            result = list_operations("http://loki:3100", limit=5)
        assert len(result) == 5

    def test_passes_label_filters(self):
        patcher, mock = _mock_loki_get({"data": {"resultType": "streams", "result": []}})
        with patcher:
            list_operations("http://loki:3100", application="myapp", area="auth", component="web")
        query = mock.call_args[0][2]["query"]
        assert "myapp" in query
        assert "auth" in query
        assert "web" in query

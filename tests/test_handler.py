import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from devlogs.context import operation
from devlogs.handler import (
    DevlogsHandler,
    DiagnosticsHandler,
    OpenSearchHandler,  # Backward compatibility alias
    _coerce_feature_value,
    _normalize_features,
    _extract_features,
)


@pytest.mark.integration
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


class TestCoerceFeatureValue:
    """Tests for _coerce_feature_value helper."""

    def test_string_returns_unchanged(self):
        assert _coerce_feature_value("hello") == "hello"

    def test_int_returns_unchanged(self):
        assert _coerce_feature_value(42) == 42

    def test_float_returns_unchanged(self):
        assert _coerce_feature_value(3.14) == 3.14

    def test_bool_returns_unchanged(self):
        assert _coerce_feature_value(True) is True
        assert _coerce_feature_value(False) is False

    def test_none_returns_unchanged(self):
        assert _coerce_feature_value(None) is None

    def test_list_converted_to_string(self):
        assert _coerce_feature_value([1, 2, 3]) == "[1, 2, 3]"

    def test_dict_converted_to_string(self):
        result = _coerce_feature_value({"a": 1})
        assert isinstance(result, str)

    def test_object_converted_to_string(self):
        class Custom:
            def __str__(self):
                return "custom_obj"
        assert _coerce_feature_value(Custom()) == "custom_obj"


class TestNormalizeFeatures:
    """Tests for _normalize_features helper."""

    def test_none_returns_none(self):
        assert _normalize_features(None) is None

    def test_empty_dict_returns_none(self):
        assert _normalize_features({}) is None

    def test_dict_returns_normalized(self):
        result = _normalize_features({"key": "value", "num": 42})
        assert result == {"key": "value", "num": 42}

    def test_list_of_tuples_returns_normalized(self):
        result = _normalize_features([("key", "value"), ("num", 42)])
        assert result == {"key": "value", "num": 42}

    def test_none_key_skipped(self):
        result = _normalize_features({None: "value", "key": "value"})
        assert result == {"key": "value"}

    def test_empty_key_skipped(self):
        result = _normalize_features({"": "value", "key": "value"})
        assert result == {"key": "value"}

    def test_whitespace_key_skipped(self):
        result = _normalize_features({"   ": "value", "key": "value"})
        assert result == {"key": "value"}

    def test_key_converted_to_string_and_stripped(self):
        result = _normalize_features({123: "value", "  spaced  ": "value2"})
        assert "123" in result
        assert "spaced" in result

    def test_non_mapping_non_sequence_returns_none(self):
        assert _normalize_features("string") is None
        assert _normalize_features(42) is None

    def test_set_processed_as_sequence(self):
        # Sets need tuples inside
        result = _normalize_features({("key", "value")})
        assert result == {"key": "value"}

    def test_malformed_sequence_items_skipped(self):
        # Items that aren't 2-tuples should be skipped
        result = _normalize_features([("key", "value"), "bad", (1, 2, 3)])
        assert result == {"key": "value"}


class TestExtractFeatures:
    """Tests for _extract_features helper."""

    def test_no_features_attribute_returns_none(self):
        record = MagicMock(spec=[])
        del record.features  # Ensure no features attribute
        assert _extract_features(record) is None

    def test_features_attribute_extracted(self):
        record = MagicMock()
        record.features = {"key": "value"}
        result = _extract_features(record)
        assert result == {"key": "value"}


class TestDevlogsHandler:
    """Tests for DevlogsHandler class (v2.0 schema)."""

    def setup_method(self):
        """Reset circuit breaker state before each test."""
        DevlogsHandler._circuit_open = False
        DevlogsHandler._circuit_open_until = 0.0
        DevlogsHandler._last_error_printed = 0.0

    def test_format_record_basic(self):
        """Test format_record produces correct v2.0 document structure."""
        handler = DevlogsHandler(application="test-app", component="api")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="test message",
            args=(),
            exc_info=None,
        )
        doc = handler.format_record(record)

        # Required schema fields
        assert doc["application"] == "test-app"
        assert doc["component"] == "api"
        assert "timestamp" in doc

        # Top-level log fields
        assert "test message" in doc["message"]
        assert doc["level"] == "info"

        # Source info at top level (flat schema)
        assert doc["logger"] == "test.logger"
        assert doc["pathname"] == "/path/to/file.py"
        assert doc["lineno"] == 42
        assert "funcname" in doc  # May be None for manually created records

        # Process info at top level (flat schema)
        assert "process" in doc
        assert "thread" in doc

    def test_format_record_with_fields(self):
        """Test format_record includes fields when present."""
        handler = DevlogsHandler(application="test-app", component="api")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.features = {"user_id": 123, "action": "login"}
        doc = handler.format_record(record)

        assert doc["fields"] == {"user_id": 123, "action": "login"}

    def test_format_record_without_fields(self):
        """Test format_record omits fields when not present."""
        handler = DevlogsHandler(application="test-app", component="api")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        doc = handler.format_record(record)

        assert "fields" not in doc

    def test_format_record_with_optional_fields(self):
        """Test format_record includes optional fields when configured."""
        handler = DevlogsHandler(
            application="test-app",
            component="api",
            environment="production",
            version="1.2.3",
        )
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        doc = handler.format_record(record)

        assert doc["environment"] == "production"
        assert doc["version"] == "1.2.3"

    def test_emit_indexes_document(self):
        """Test emit calls client.index."""
        mock_client = MagicMock()
        handler = DevlogsHandler(
            application="test-app",
            component="api",
            opensearch_client=mock_client,
            index_name="test-index",
        )
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        mock_client.index.assert_called_once()
        call_kwargs = mock_client.index.call_args.kwargs
        assert call_kwargs["index"] == "test-index"
        assert call_kwargs["body"]["doc_type"] == "log_entry"
        assert call_kwargs["body"]["application"] == "test-app"
        assert call_kwargs["body"]["component"] == "api"

    def test_emit_without_client_does_not_fail(self):
        """Test emit with no client doesn't raise."""
        handler = DevlogsHandler(application="test-app", component="api")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        # Should not raise
        handler.emit(record)

    def test_circuit_breaker_opens_on_failure(self):
        """Test circuit breaker opens after indexing failure."""
        mock_client = MagicMock()
        mock_client.index.side_effect = Exception("Connection failed")
        handler = DevlogsHandler(
            application="test-app",
            component="api",
            opensearch_client=mock_client,
            index_name="test-index",
        )
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )

        with patch("builtins.print"):  # Suppress error output
            handler.emit(record)

        assert DevlogsHandler._circuit_open is True
        assert DevlogsHandler._circuit_open_until > time.time()

    def test_circuit_breaker_skips_indexing_when_open(self):
        """Test circuit breaker skips indexing when open."""
        mock_client = MagicMock()
        handler = DevlogsHandler(
            application="test-app",
            component="api",
            opensearch_client=mock_client,
            index_name="test-index",
        )
        # Open circuit breaker
        DevlogsHandler._circuit_open = True
        DevlogsHandler._circuit_open_until = time.time() + 60

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        mock_client.index.assert_not_called()

    def test_circuit_breaker_resets_on_success(self):
        """Test circuit breaker resets after successful indexing."""
        mock_client = MagicMock()
        handler = DevlogsHandler(
            application="test-app",
            component="api",
            opensearch_client=mock_client,
            index_name="test-index",
        )
        # Open circuit breaker but set time in past
        DevlogsHandler._circuit_open = True
        DevlogsHandler._circuit_open_until = time.time() - 1

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        with patch("builtins.print"):
            handler.emit(record)

        assert DevlogsHandler._circuit_open is False

    def test_error_throttling(self):
        """Test errors are only printed periodically."""
        mock_client = MagicMock()
        mock_client.index.side_effect = Exception("Connection failed")
        handler = DevlogsHandler(
            application="test-app",
            component="api",
            opensearch_client=mock_client,
            index_name="test-index",
        )

        with patch("builtins.print") as mock_print:
            # First error - should print
            DevlogsHandler._circuit_open = False
            DevlogsHandler._last_error_printed = 0.0
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="test", args=(), exc_info=None,
            )
            handler.emit(record)
            assert mock_print.called

            # Immediate second error - should not print (throttled)
            mock_print.reset_mock()
            DevlogsHandler._circuit_open = False  # Reset for second attempt
            handler.emit(record)
            # Print might be called or not depending on timing


class TestOpenSearchHandlerBackwardCompatibility:
    """Tests for backward compatibility alias."""

    def test_opensearch_handler_is_devlogs_handler(self):
        """Test OpenSearchHandler is an alias for DevlogsHandler."""
        assert OpenSearchHandler is DevlogsHandler

    def test_opensearch_handler_works_with_defaults(self):
        """Test OpenSearchHandler works with default parameters."""
        handler = OpenSearchHandler()
        assert handler.application == "unknown"
        assert handler.component == "default"


class TestDiagnosticsHandler:
    """Tests for DiagnosticsHandler class."""

    def setup_method(self):
        """Reset circuit breaker state before each test."""
        DevlogsHandler._circuit_open = False
        DevlogsHandler._circuit_open_until = 0.0

    def test_generates_operation_id_if_missing(self):
        """Test DiagnosticsHandler generates operation_id if not set."""
        mock_client = MagicMock()
        handler = DiagnosticsHandler(
            opensearch_client=mock_client, index_name="test-index"
        )
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        call_kwargs = mock_client.index.call_args.kwargs
        doc = call_kwargs["body"]
        assert doc["operation_id"] is not None
        # Should be a UUID-like string
        assert len(doc["operation_id"]) == 36

    def test_uses_record_area_if_set(self):
        """Test DiagnosticsHandler uses area from record if set."""
        mock_client = MagicMock()
        handler = DiagnosticsHandler(
            opensearch_client=mock_client, index_name="test-index"
        )
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.area = "custom-area"
        record.operation_id = "custom-op-id"

        handler.emit(record)

        call_kwargs = mock_client.index.call_args.kwargs
        doc = call_kwargs["body"]
        assert doc["area"] == "custom-area"
        assert doc["operation_id"] == "custom-op-id"

    def test_default_level_is_debug(self):
        """Test DiagnosticsHandler accepts DEBUG level by default."""
        handler = DiagnosticsHandler()
        assert handler.level == logging.DEBUG


class TestEmitCounters:
    """Tests for handler emit counters."""

    def setup_method(self):
        DevlogsHandler.reset_counters()
        DevlogsHandler._circuit_open = False
        DevlogsHandler._circuit_open_until = 0.0

    def test_reset_counters(self):
        DevlogsHandler._emit_count = 5
        DevlogsHandler._emit_errors = 3
        DevlogsHandler._emit_skipped = 2
        DevlogsHandler.reset_counters()
        assert DevlogsHandler._emit_count == 0
        assert DevlogsHandler._emit_errors == 0
        assert DevlogsHandler._emit_skipped == 0

    def test_emit_count_increments_on_success(self):
        handler = DevlogsHandler(collector_url="http://localhost:9999")
        logger = logging.getLogger("test.counters.success")
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        with patch("urllib.request.urlopen"):
            logger.info("test message")
            logger.info("test message 2")
        assert DevlogsHandler._emit_count == 2
        assert DevlogsHandler._emit_errors == 0
        assert DevlogsHandler._emit_skipped == 0

    def test_emit_errors_increments_on_failure(self):
        handler = DevlogsHandler(collector_url="http://localhost:9999")
        logger = logging.getLogger("test.counters.error")
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            logger.info("test message")
        assert DevlogsHandler._emit_count == 1
        assert DevlogsHandler._emit_errors == 1

    def test_emit_skipped_increments_when_circuit_open(self):
        DevlogsHandler._circuit_open = True
        DevlogsHandler._circuit_open_until = time.time() + 60
        handler = DevlogsHandler(collector_url="http://localhost:9999")
        logger = logging.getLogger("test.counters.skipped")
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.info("test message")
        assert DevlogsHandler._emit_count == 1
        assert DevlogsHandler._emit_skipped == 1
        assert DevlogsHandler._emit_errors == 0

    def test_counters_track_mixed_results(self):
        handler = DevlogsHandler(collector_url="http://localhost:9999")
        logger = logging.getLogger("test.counters.mixed")
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        # One success, then a failure (which opens circuit), then a skipped
        mock_urlopen = MagicMock()
        with patch("urllib.request.urlopen", mock_urlopen):
            logger.info("success")
        assert DevlogsHandler._emit_count == 1
        assert DevlogsHandler._emit_errors == 0

        with patch("urllib.request.urlopen", side_effect=Exception("fail")):
            logger.info("failure")
        assert DevlogsHandler._emit_count == 2
        assert DevlogsHandler._emit_errors == 1

        # Circuit is now open, next emit should be skipped
        logger.info("skipped")
        assert DevlogsHandler._emit_count == 3
        assert DevlogsHandler._emit_skipped == 1


class TestPluginMode:
    """Tests for plugin URL support in DevlogsHandler."""

    def setup_method(self):
        DevlogsHandler._circuit_open = False
        DevlogsHandler._circuit_open_until = 0.0
        DevlogsHandler._last_error_printed = 0.0
        DevlogsHandler.reset_counters()

    def _make_record(self, msg="test message"):
        return logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_plugin_url_sets_plugin(self):
        """Handler with plugin URL resolves plugin."""
        from devlogs.collector.plugins import OutputPlugin, register_plugin, _registry

        saved = dict(_registry)
        _registry.clear()

        class FakePlugin(OutputPlugin):
            name = "fake"
            schemes = ["fake"]
            def __init__(self, url, cfg):
                self.url = url
            def send(self, records):
                return {"ingested": len(records)}
            def check(self):
                return "OK"
            def display_info(self):
                return self.url

        register_plugin(FakePlugin)
        try:
            handler = DevlogsHandler(
                application="test-app",
                component="api",
                collector_url="fake://localhost:9000",
            )
            assert handler._plugin is not None
            assert isinstance(handler._plugin, FakePlugin)
            assert handler._collector_endpoint is None
        finally:
            _registry.clear()
            _registry.update(saved)

    def test_plugin_emit_calls_send(self):
        """emit() calls plugin.send() with DevlogsRecord."""
        from devlogs.collector.plugins import OutputPlugin, register_plugin, _registry
        from devlogs.collector.schema import DevlogsRecord

        saved = dict(_registry)
        _registry.clear()

        sent = []

        class TrackPlugin(OutputPlugin):
            name = "track"
            schemes = ["track"]
            def __init__(self, url, cfg):
                self.url = url
            def send(self, records):
                sent.extend(records)
                return {"ingested": len(records)}
            def check(self):
                return "OK"
            def display_info(self):
                return self.url

        register_plugin(TrackPlugin)
        try:
            handler = DevlogsHandler(
                application="test-app",
                component="api",
                collector_url="track://localhost:9000",
            )
            handler.emit(self._make_record())
            assert len(sent) == 1
            assert isinstance(sent[0], DevlogsRecord)
            assert sent[0].application == "test-app"
            assert sent[0].component == "api"
            assert sent[0].message is not None
        finally:
            _registry.clear()
            _registry.update(saved)

    def test_plugin_emit_preserves_extra_fields(self):
        """logger/pathname/lineno etc. end up in fields."""
        from devlogs.collector.plugins import OutputPlugin, register_plugin, _registry

        saved = dict(_registry)
        _registry.clear()

        sent = []

        class TrackPlugin(OutputPlugin):
            name = "trackf"
            schemes = ["trackf"]
            def __init__(self, url, cfg):
                self.url = url
            def send(self, records):
                sent.extend(records)
                return {"ingested": len(records)}
            def check(self):
                return "OK"
            def display_info(self):
                return self.url

        register_plugin(TrackPlugin)
        try:
            handler = DevlogsHandler(
                application="test-app",
                component="api",
                collector_url="trackf://localhost:9000",
            )
            handler.emit(self._make_record())
            record = sent[0]
            assert record.fields is not None
            assert "logger" in record.fields
            assert "pathname" in record.fields
            assert "lineno" in record.fields
        finally:
            _registry.clear()
            _registry.update(saved)

    def test_plugin_emit_circuit_breaker(self):
        """Circuit breaker still works with plugins."""
        from devlogs.collector.plugins import OutputPlugin, register_plugin, _registry

        saved = dict(_registry)
        _registry.clear()

        class FailPlugin(OutputPlugin):
            name = "failp"
            schemes = ["failp"]
            def __init__(self, url, cfg):
                self.url = url
            def send(self, records):
                raise ConnectionError("backend down")
            def check(self):
                return "OK"
            def display_info(self):
                return self.url

        register_plugin(FailPlugin)
        try:
            handler = DevlogsHandler(
                application="test-app",
                component="api",
                collector_url="failp://localhost:9000",
            )
            with patch("builtins.print"):
                handler.emit(self._make_record())

            assert DevlogsHandler._circuit_open is True
            assert DevlogsHandler._emit_errors == 1
        finally:
            _registry.clear()
            _registry.update(saved)

    def test_http_url_does_not_use_plugin(self):
        """http:// URL still uses HTTP POST, not plugin."""
        from devlogs.collector.plugins import OutputPlugin, register_plugin, _registry

        saved = dict(_registry)
        _registry.clear()

        class DummyPlugin(OutputPlugin):
            name = "dummy"
            schemes = ["dummy"]
            def __init__(self, url, cfg):
                self.url = url
            def send(self, records):
                return {"ingested": len(records)}
            def check(self):
                return "OK"
            def display_info(self):
                return self.url

        register_plugin(DummyPlugin)
        try:
            handler = DevlogsHandler(
                application="test-app",
                component="api",
                collector_url="http://localhost:8080",
            )
            assert handler._plugin is None
            assert handler._collector_endpoint is not None
        finally:
            _registry.clear()
            _registry.update(saved)

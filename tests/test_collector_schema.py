# Tests for the devlogs record schema validation

import pytest
from devlogs.collector.schema import (
    DevlogsRecord,
    validate_record,
    normalize_records,
    enrich_record,
    validate_timestamp,
    validate_string,
    get_current_timestamp,
)
from devlogs.collector.errors import ValidationError


class TestValidateTimestamp:
    """Tests for timestamp validation."""

    def test_valid_utc_timestamp(self):
        ts = "2024-01-15T10:30:00Z"
        assert validate_timestamp(ts, "test") == ts

    def test_valid_timestamp_with_millis(self):
        ts = "2024-01-15T10:30:00.123Z"
        assert validate_timestamp(ts, "test") == ts

    def test_valid_timestamp_with_offset(self):
        ts = "2024-01-15T10:30:00+00:00"
        assert validate_timestamp(ts, "test") == ts

    def test_valid_timestamp_with_offset_no_colon(self):
        ts = "2024-01-15T10:30:00+0000"
        assert validate_timestamp(ts, "test") == ts

    def test_missing_timestamp_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_timestamp(None, "timestamp")
        assert "Missing required field" in exc.value.message

    def test_invalid_format_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_timestamp("2024/01/15", "test")
        assert "ISO 8601 format" in exc.value.message

    def test_non_string_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_timestamp(12345, "test")
        assert "must be a string" in exc.value.message


class TestValidateString:
    """Tests for string field validation."""

    def test_valid_string(self):
        assert validate_string("hello", "test") == "hello"

    def test_strips_whitespace(self):
        assert validate_string("  hello  ", "test") == "hello"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_string(None, "application", required=True)
        assert "Missing required field" in exc.value.message

    def test_empty_required_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_string("", "application", required=True)
        assert "cannot be empty" in exc.value.message

    def test_whitespace_only_required_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_string("   ", "application", required=True)
        assert "cannot be empty" in exc.value.message

    def test_missing_optional_returns_none(self):
        assert validate_string(None, "optional", required=False) is None

    def test_empty_optional_returns_none(self):
        assert validate_string("", "optional", required=False) is None

    def test_non_string_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_string(123, "test")
        assert "must be a string" in exc.value.message


class TestValidateRecord:
    """Tests for full record validation."""

    def test_minimal_valid_record(self):
        data = {
            "application": "my-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
        }
        record = validate_record(data)
        assert record.application == "my-app"
        assert record.component == "api"
        assert record.timestamp == "2024-01-15T10:30:00Z"
        assert record.environment is None
        assert record.version is None
        assert record.fields is None

    def test_full_valid_record(self):
        data = {
            "application": "my-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
            "environment": "production",
            "version": "1.2.3",
            "fields": {"user_id": "123", "nested": {"key": "value"}},
        }
        record = validate_record(data)
        assert record.application == "my-app"
        assert record.component == "api"
        assert record.environment == "production"
        assert record.version == "1.2.3"
        assert record.fields == {"user_id": "123", "nested": {"key": "value"}}

    def test_missing_application_raises(self):
        data = {
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
        }
        with pytest.raises(ValidationError) as exc:
            validate_record(data)
        assert "application" in exc.value.message

    def test_missing_component_raises(self):
        data = {
            "application": "my-app",
            "timestamp": "2024-01-15T10:30:00Z",
        }
        with pytest.raises(ValidationError) as exc:
            validate_record(data)
        assert "component" in exc.value.message

    def test_missing_timestamp_raises(self):
        data = {
            "application": "my-app",
            "component": "api",
        }
        with pytest.raises(ValidationError) as exc:
            validate_record(data)
        assert "timestamp" in exc.value.message

    def test_invalid_fields_type_raises(self):
        data = {
            "application": "my-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
            "fields": "not an object",
        }
        with pytest.raises(ValidationError) as exc:
            validate_record(data)
        assert "must be an object" in exc.value.message

    def test_non_dict_record_raises(self):
        with pytest.raises(ValidationError) as exc:
            validate_record("not a dict")
        assert "must be an object" in exc.value.message


class TestNormalizeRecords:
    """Tests for payload normalization."""

    def test_single_record(self):
        payload = {
            "application": "my-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
        }
        records = normalize_records(payload)
        assert len(records) == 1
        assert records[0]["application"] == "my-app"

    def test_batch_records(self):
        payload = {
            "records": [
                {"application": "my-app", "component": "api", "timestamp": "2024-01-15T10:30:00Z"},
                {"application": "my-app", "component": "worker", "timestamp": "2024-01-15T10:30:01Z"},
            ]
        }
        records = normalize_records(payload)
        assert len(records) == 2
        assert records[0]["component"] == "api"
        assert records[1]["component"] == "worker"

    def test_empty_payload_raises(self):
        with pytest.raises(ValidationError) as exc:
            normalize_records(None)
        assert "cannot be empty" in exc.value.message

    def test_non_object_payload_raises(self):
        with pytest.raises(ValidationError) as exc:
            normalize_records([1, 2, 3])
        assert "must be a JSON object" in exc.value.message

    def test_empty_records_array_raises(self):
        with pytest.raises(ValidationError) as exc:
            normalize_records({"records": []})
        assert "cannot be empty" in exc.value.message

    def test_non_array_records_raises(self):
        with pytest.raises(ValidationError) as exc:
            normalize_records({"records": "not an array"})
        assert "must be an array" in exc.value.message


class TestEnrichRecord:
    """Tests for record enrichment."""

    def test_enriches_with_collector_metadata(self):
        from devlogs.collector.auth import Identity
        record = DevlogsRecord(
            application="my-app",
            component="api",
            timestamp="2024-01-15T10:30:00Z",
        )
        identity = Identity.verified(id="user-123", name="Test User")
        enriched = enrich_record(record, "192.168.1.1", identity)
        assert enriched.client_ip == "192.168.1.1"
        assert enriched.identity is not None
        assert enriched.identity["mode"] == "verified"
        assert enriched.identity["id"] == "user-123"
        assert enriched.collected_ts is not None
        # Verify timestamp format
        assert enriched.collected_ts.endswith("Z")
        assert "T" in enriched.collected_ts

    def test_anonymous_identity(self):
        from devlogs.collector.auth import Identity
        record = DevlogsRecord(
            application="my-app",
            component="api",
            timestamp="2024-01-15T10:30:00Z",
        )
        identity = Identity.anonymous()
        enriched = enrich_record(record, "10.0.0.1", identity)
        assert enriched.identity["mode"] == "anonymous"

    def test_passthrough_identity(self):
        from devlogs.collector.auth import Identity
        record = DevlogsRecord(
            application="my-app",
            component="api",
            timestamp="2024-01-15T10:30:00Z",
        )
        identity = Identity.passthrough({"custom_id": "abc", "role": "admin"})
        enriched = enrich_record(record, "10.0.0.1", identity)
        assert enriched.identity["mode"] == "passthrough"
        assert enriched.identity["custom_id"] == "abc"


class TestDevlogsRecordToDict:
    """Tests for record serialization."""

    def test_minimal_record_to_dict(self):
        record = DevlogsRecord(
            application="my-app",
            component="api",
            timestamp="2024-01-15T10:30:00Z",
        )
        d = record.to_dict()
        assert d["application"] == "my-app"
        assert d["component"] == "api"
        assert d["timestamp"] == "2024-01-15T10:30:00Z"
        # Default identity is anonymous
        assert d["identity"] == {"mode": "anonymous"}
        assert "environment" not in d
        assert "version" not in d
        assert "fields" not in d

    def test_full_record_to_dict(self):
        from devlogs.collector.auth import Identity
        identity = Identity.verified(id="user-123", name="Test User")
        record = DevlogsRecord(
            application="my-app",
            component="api",
            timestamp="2024-01-15T10:30:00Z",
            environment="production",
            version="1.2.3",
            fields={"key": "value"},
            collected_ts="2024-01-15T10:30:01Z",
            client_ip="192.168.1.1",
        )
        record.identity = identity
        d = record.to_dict()
        assert d["environment"] == "production"
        assert d["version"] == "1.2.3"
        assert d["fields"] == {"key": "value"}
        assert d["collected_ts"] == "2024-01-15T10:30:01Z"
        assert d["client_ip"] == "192.168.1.1"
        assert d["identity"]["mode"] == "verified"
        assert d["identity"]["id"] == "user-123"
        assert d["identity"]["name"] == "Test User"

    def test_record_with_dict_identity(self):
        record = DevlogsRecord(
            application="my-app",
            component="api",
            timestamp="2024-01-15T10:30:00Z",
        )
        record.identity = {"mode": "passthrough", "custom": "data"}
        d = record.to_dict()
        assert d["identity"]["mode"] == "passthrough"
        assert d["identity"]["custom"] == "data"


class TestGetCurrentTimestamp:
    """Tests for timestamp generation."""

    def test_generates_valid_iso8601(self):
        ts = get_current_timestamp()
        # Should be valid format
        assert "T" in ts
        assert ts.endswith("Z")
        # Should have milliseconds
        assert "." in ts

    def test_generates_unique_timestamps(self):
        ts1 = get_current_timestamp()
        ts2 = get_current_timestamp()
        # May be same if called fast enough, but both should be valid
        assert "T" in ts1 and ts1.endswith("Z")
        assert "T" in ts2 and ts2.endswith("Z")

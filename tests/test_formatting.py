import pytest
from datetime import datetime, timezone
from devlogs.formatting import format_timestamp, format_level, format_entry_text


def test_format_timestamp_utc():
	"""Test formatting timestamp in UTC mode."""
	# Test with Z-suffix format
	timestamp = "2024-01-15T10:30:45.123Z"
	result = format_timestamp(timestamp, use_utc=True)
	assert result.startswith("2024-01-15T10:30:45.")
	assert result.endswith("Z")


def test_format_timestamp_local():
	"""Test formatting timestamp in local time mode."""
	# Test with Z-suffix format
	timestamp = "2024-01-15T10:30:45.123Z"
	result = format_timestamp(timestamp, use_utc=False)
	# Should return timestamp without Z suffix (local time)
	assert result.startswith("2024-01-15T")
	assert "Z" not in result
	# Check format is correct (YYYY-MM-DDTHH:MM:SS.mmm)
	assert len(result) == 23  # Format: 2024-01-15T10:30:45.123


def test_format_timestamp_with_timezone_offset():
	"""Test formatting timestamp with +00:00 format."""
	timestamp = "2024-01-15T10:30:45.123+00:00"
	result = format_timestamp(timestamp, use_utc=True)
	assert result.startswith("2024-01-15T10:30:45.")
	assert result.endswith("Z")


def test_format_timestamp_empty():
	"""Test formatting empty timestamp."""
	result = format_timestamp("", use_utc=False)
	assert result == ""
	
	result = format_timestamp("", use_utc=True)
	assert result == ""


def test_format_timestamp_none():
	"""Test formatting None timestamp."""
	result = format_timestamp(None, use_utc=False)
	assert result == ""


def test_format_timestamp_invalid():
	"""Test formatting invalid timestamp."""
	timestamp = "invalid-timestamp"
	result = format_timestamp(timestamp, use_utc=False)
	# Should return original string on parse failure
	assert result == "invalid-timestamp"


class TestFormatLevel:
	def test_known_levels(self):
		assert format_level("info") == "[i]"
		assert format_level("error") == "[e]"
		assert format_level("warning") == "[w]"
		assert format_level("debug") == "[d]"
		assert format_level("critical") == "[c]"

	def test_none_level(self):
		assert format_level(None) == "   "

	def test_unknown_level(self):
		assert format_level("trace") == "[t]"

	def test_color(self):
		result = format_level("error", color=True)
		assert "\033[31m" in result  # red
		assert "[e]" in result
		assert "\033[0m" in result  # reset

	def test_no_color(self):
		result = format_level("error", color=False)
		assert "\033[" not in result


class TestFormatEntryText:
	def test_basic_entry(self):
		doc = {
			"timestamp": "2024-01-15T10:30:45.123Z",
			"level": "info",
			"area": "web",
			"operation_id": "op-1",
			"message": "hello world",
		}
		line = format_entry_text(doc, use_utc=True)
		assert "[i]" in line
		assert "web" in line
		assert "op-1" in line
		assert "hello world" in line

	def test_color_dims_metadata(self):
		doc = {
			"timestamp": "2024-01-15T10:30:45.123Z",
			"level": "error",
			"area": "api",
			"operation_id": "op-2",
			"message": "bad request",
		}
		line = format_entry_text(doc, use_utc=True, color=True)
		assert "\033[31m" in line  # red for error level
		assert "\033[2m" in line   # dim for metadata
		assert "bad request" in line

	def test_no_area_or_operation(self):
		doc = {
			"timestamp": "2024-01-15T10:30:45.123Z",
			"level": "debug",
			"message": "just a message",
		}
		line = format_entry_text(doc, use_utc=True)
		assert "[d]" in line
		assert "just a message" in line

	def test_with_features(self):
		doc = {
			"timestamp": "2024-01-15T10:30:45.123Z",
			"level": "info",
			"area": "web",
			"operation_id": "op-1",
			"message": "hello",
			"fields": {"env": "prod"},
		}
		fmt_fn = lambda f: f"[env={f['env']}]" if f else ""
		line = format_entry_text(doc, use_utc=True, format_features_fn=fmt_fn)
		assert "[env=prod]" in line

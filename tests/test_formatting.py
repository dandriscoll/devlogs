import pytest
from datetime import datetime, timezone
from devlogs.formatting import format_timestamp


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

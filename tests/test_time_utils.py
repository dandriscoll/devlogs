from datetime import datetime, timezone

from devlogs.time_utils import resolve_relative_time


def test_resolve_relative_time_hours():
	now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
	assert resolve_relative_time("1h", now=now) == "2025-01-01T11:00:00.000Z"


def test_resolve_relative_time_minutes():
	now = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
	assert resolve_relative_time("90m", now=now) == "2025-01-01T10:30:30.000Z"


def test_resolve_relative_time_passthrough():
	value = "2025-01-01T00:00:00Z"
	assert resolve_relative_time(value) == value

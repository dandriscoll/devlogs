# Formatting utilities for devlogs output

from datetime import datetime, timezone
from typing import Iterable, Dict, Any


def format_timestamp(timestamp_str: str | None, use_utc: bool = False, omit_date: bool = False) -> str:
	"""
	Format a timestamp string for display.

	Args:
		timestamp_str: ISO 8601 timestamp string (typically UTC with Z suffix) or None
		use_utc: If True, display in UTC; if False, display in local time
		omit_date: If True, show only time portion (HH:MM:SS.mmm)

	Returns:
		Formatted timestamp string
	"""
	if not timestamp_str:
		return ""

	try:
		# Parse the ISO timestamp (handles Z suffix and +00:00 format)
		dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

		if use_utc:
			dt_display = dt.astimezone(timezone.utc)
			if omit_date:
				return dt_display.strftime("%H:%M:%S.%f")[:-3] + "Z"
			return dt_display.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
		else:
			dt_display = dt.astimezone()
			if omit_date:
				return dt_display.strftime("%H:%M:%S.%f")[:-3]
			return dt_display.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
	except (ValueError, AttributeError):
		# If parsing fails, return original string
		return timestamp_str


def all_entries_today(entries: Iterable[Dict[str, Any]], use_utc: bool = False) -> bool:
	"""Check if all entries have timestamps from today.

	Args:
		entries: Log entries with 'timestamp' keys
		use_utc: If True, compare against UTC date; otherwise local date

	Returns:
		True if all entries are from today (or have no timestamp)
	"""
	if use_utc:
		today = datetime.now(timezone.utc).date()
	else:
		today = datetime.now().astimezone().date()
	has_any = False
	for entry in entries:
		ts = entry.get("timestamp")
		if not ts:
			continue
		has_any = True
		try:
			dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
			if use_utc:
				entry_date = dt.astimezone(timezone.utc).date()
			else:
				entry_date = dt.astimezone().date()
			if entry_date != today:
				return False
		except (ValueError, AttributeError):
			return False
	return has_any

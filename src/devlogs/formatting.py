# Formatting utilities for devlogs output

from datetime import datetime, timezone


def format_timestamp(timestamp_str: str | None, use_utc: bool = False) -> str:
	"""
	Format a timestamp string for display.
	
	Args:
		timestamp_str: ISO 8601 timestamp string (typically UTC with Z suffix) or None
		use_utc: If True, display in UTC; if False, display in local time
	
	Returns:
		Formatted timestamp string
	"""
	if not timestamp_str:
		return ""
	
	try:
		# Parse the ISO timestamp (handles Z suffix and +00:00 format)
		dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
		
		if use_utc:
			# Keep in UTC, format as ISO-like string
			dt_utc = dt.astimezone(timezone.utc)
			return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
		else:
			# Convert to local time
			dt_local = dt.astimezone()
			return dt_local.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
	except (ValueError, AttributeError):
		# If parsing fails, return original string
		return timestamp_str

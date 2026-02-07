# Formatting utilities for devlogs output

from datetime import datetime, timezone
from typing import Iterable, Dict, Any


_LEVEL_BADGES = {
	"debug":    "[d]",
	"info":     "[i]",
	"warning":  "[w]",
	"error":    "[e]",
	"critical": "[c]",
}

# ANSI color codes
_LEVEL_COLORS = {
	"debug":    "\033[36m",   # cyan
	"info":     "\033[32m",   # green
	"warning":  "\033[33m",   # yellow
	"error":    "\033[31m",   # red
	"critical": "\033[35m",   # magenta
}
_DIM = "\033[2m"
_RESET = "\033[0m"


def format_level(level: str | None, color: bool = False) -> str:
	"""Format a log level as a short badge like [i], [e], [w].

	Args:
		level: Normalized level string (e.g. "info", "error")
		color: If True, wrap in ANSI color codes
	"""
	if not level:
		return "   "
	badge = _LEVEL_BADGES.get(level, f"[{level[0]}]" if level else "   ")
	if color:
		ansi = _LEVEL_COLORS.get(level, "")
		if ansi:
			return f"{ansi}{badge}{_RESET}"
	return badge


def format_entry_text(doc: Dict[str, Any], *, use_utc: bool = False,
                      omit_date: bool = False, color: bool = False,
                      format_features_fn=None) -> str:
	"""Format a normalized log entry as a human-readable text line.

	Args:
		doc: Normalized log entry dict
		use_utc: Display timestamps in UTC
		omit_date: Omit date portion of timestamp
		color: Use ANSI colors
		format_features_fn: Callable to format the fields dict
	"""
	timestamp = format_timestamp(doc.get("timestamp") or "", use_utc=use_utc, omit_date=omit_date)
	level = format_level(doc.get("level"), color=color)
	area = doc.get("area") or ""
	operation = doc.get("operation_id") or ""
	message = doc.get("message") or ""
	features = format_features_fn(doc.get("fields")) if format_features_fn else ""

	dim = _DIM if color else ""
	reset = _RESET if color else ""

	meta = f"{dim}{area} {operation}{reset}" if (area or operation) else ""
	if features:
		meta = f"{meta} {dim}{features}{reset}" if meta else f"{dim}{features}{reset}"

	parts = [timestamp, level]
	if meta:
		parts.append(meta)
	parts.append(message)
	return " ".join(parts)


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

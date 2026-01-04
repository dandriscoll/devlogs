# Time utilities for devlogs filtering

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Optional


_RELATIVE_TIME_RE = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)


def resolve_relative_time(value: Optional[str], *, now: Optional[datetime] = None) -> Optional[str]:
	"""Resolve relative time strings like '1h' into an ISO 8601 UTC timestamp."""
	if value is None or not isinstance(value, str):
		return value
	match = _RELATIVE_TIME_RE.match(value)
	if not match:
		return value
	amount = int(match.group(1))
	unit = match.group(2).lower()
	if unit == "s":
		delta = timedelta(seconds=amount)
	elif unit == "m":
		delta = timedelta(minutes=amount)
	elif unit == "h":
		delta = timedelta(hours=amount)
	elif unit == "d":
		delta = timedelta(days=amount)
	elif unit == "w":
		delta = timedelta(weeks=amount)
	else:
		return value
	if now is None:
		now = datetime.now(timezone.utc)
	target = now - delta
	return target.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

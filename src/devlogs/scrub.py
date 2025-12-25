# Scrubbing/pruning old DEBUG entries

from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import load_config

DEFAULT_RETENTION_DEBUG_HOURS = 24.0


def _coerce_hours(value: Optional[object]) -> Optional[float]:
	if value is None:
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _resolve_retention_hours(older_than_hours: Optional[float]) -> float:
	"""Resolve retention hours (runtime override > env > default)."""
	override = _coerce_hours(older_than_hours)
	if override is not None:
		return override
	cfg = load_config()
	env_value = _coerce_hours(getattr(cfg, "retention_debug_hours", None))
	if env_value is not None:
		return env_value
	return DEFAULT_RETENTION_DEBUG_HOURS


def _to_iso(dt: datetime) -> str:
	return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def scrub_debug_logs(client, index, older_than_hours: Optional[float] = None, now: Optional[datetime] = None) -> int:
	"""Delete DEBUG-level log entries older than specified hours."""
	retention_hours = _resolve_retention_hours(older_than_hours)
	if retention_hours <= 0:
		return 0
	if now is None:
		now = datetime.now(timezone.utc)
	elif now.tzinfo is None:
		now = now.replace(tzinfo=timezone.utc)
	cutoff = now - timedelta(hours=retention_hours)
	response = client.delete_by_query(
		index=index,
		body={
			"query": {
				"bool": {
					"filter": [
						{"term": {"level": "debug"}},
						{"range": {"timestamp": {"lt": _to_iso(cutoff)}}},
					]
				}
			}
		},
		refresh=False,
		conflicts="proceed",
		slices="auto",
	)
	if isinstance(response, dict):
		return int(response.get("deleted", 0))
	return 0

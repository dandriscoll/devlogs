# Time-based log retention and cleanup

from datetime import datetime, timedelta, timezone
from typing import Optional
from .config import DevlogsConfig


def cleanup_old_logs(client, config: DevlogsConfig, dry_run: bool = False) -> dict:
	"""Clean up old logs based on retention policy.

	Retention tiers:
	- DEBUG logs: Deleted after retention_debug_hours (default: 6 hours)
	- INFO logs: Deleted after retention_info_days (default: 7 days)
	- WARNING/ERROR/CRITICAL: Deleted after retention_warning_days (default: 30 days)

	Args:
		client: OpenSearch client
		config: DevlogsConfig instance with retention settings
		dry_run: If True, only count documents without deleting

	Returns:
		dict with counts of documents deleted per tier
	"""
	now = datetime.now(timezone.utc)
	index = config.index_logs

	results = {
		"debug_deleted": 0,
		"info_deleted": 0,
		"warning_deleted": 0,
		"dry_run": dry_run
	}

	# Tier 1: Delete DEBUG logs older than retention_debug_hours
	debug_cutoff = now - timedelta(hours=config.retention_debug_hours)
	debug_count = _delete_by_level_and_time(
		client, index, "debug", debug_cutoff, dry_run
	)
	results["debug_deleted"] = debug_count

	# Tier 2: Delete INFO logs older than retention_info_days
	info_cutoff = now - timedelta(days=config.retention_info_days)
	info_count = _delete_by_level_and_time(
		client, index, "info", info_cutoff, dry_run
	)
	results["info_deleted"] = info_count

	# Tier 3: Delete WARNING/ERROR/CRITICAL logs older than retention_warning_days
	warning_cutoff = now - timedelta(days=config.retention_warning_days)
	warning_count = _delete_by_time(
		client, index, warning_cutoff, dry_run
	)
	results["warning_deleted"] = warning_count

	return results


def _delete_by_level_and_time(
	client, index: str, level: str, cutoff: datetime, dry_run: bool
) -> int:
	"""Delete logs of a specific level older than cutoff time."""
	query = {
		"bool": {
			"filter": [
				{"term": {"level": level}},
				{"range": {"timestamp": {"lt": cutoff.isoformat()}}}
			]
		}
	}

	if dry_run:
		# Count only
		response = client.count(index=index, body={"query": query})
		return response.get("count", 0)
	else:
		# Delete
		response = client.delete_by_query(
			index=index,
			body={"query": query},
			conflicts="proceed",
			refresh=False
		)
		return response.get("deleted", 0)


def _delete_by_time(client, index: str, cutoff: datetime, dry_run: bool) -> int:
	"""Delete all logs older than cutoff time (any level)."""
	query = {
		"range": {"timestamp": {"lt": cutoff.isoformat()}}
	}

	if dry_run:
		# Count only
		response = client.count(index=index, body={"query": query})
		return response.get("count", 0)
	else:
		# Delete
		response = client.delete_by_query(
			index=index,
			body={"query": query},
			conflicts="proceed",
			refresh=False
		)
		return response.get("deleted", 0)


def get_retention_stats(client, config: DevlogsConfig) -> dict:
	"""Get statistics about logs eligible for deletion.

	Returns:
		dict with counts of documents in each retention tier
	"""
	now = datetime.now(timezone.utc)
	index = config.index_logs

	debug_cutoff = now - timedelta(hours=config.retention_debug_hours)
	info_cutoff = now - timedelta(days=config.retention_info_days)
	warning_cutoff = now - timedelta(days=config.retention_warning_days)

	stats = {
		"total_logs": 0,
		"hot_tier": 0,  # Recent logs (< debug_cutoff)
		"eligible_for_deletion": {
			"debug": 0,  # DEBUG logs older than debug_cutoff
			"info": 0,   # INFO logs older than info_cutoff
			"all": 0     # All logs older than warning_cutoff
		}
	}

	# Get total count
	total_response = client.count(index=index)
	stats["total_logs"] = total_response.get("count", 0)

	# Get hot tier count (recent logs)
	hot_response = client.count(
		index=index,
		body={
			"query": {
				"range": {"timestamp": {"gte": debug_cutoff.isoformat()}}
			}
		}
	)
	stats["hot_tier"] = hot_response.get("count", 0)

	# Get counts eligible for deletion
	debug_response = client.count(
		index=index,
		body={
			"query": {
				"bool": {
					"filter": [
						{"term": {"level": "debug"}},
						{"range": {"timestamp": {"lt": debug_cutoff.isoformat()}}}
					]
				}
			}
		}
	)
	stats["eligible_for_deletion"]["debug"] = debug_response.get("count", 0)

	info_response = client.count(
		index=index,
		body={
			"query": {
				"bool": {
					"filter": [
						{"term": {"level": "info"}},
						{"range": {"timestamp": {"lt": info_cutoff.isoformat()}}}
					]
				}
			}
		}
	)
	stats["eligible_for_deletion"]["info"] = info_response.get("count", 0)

	all_old_response = client.count(
		index=index,
		body={
			"query": {
				"range": {"timestamp": {"lt": warning_cutoff.isoformat()}}
			}
		}
	)
	stats["eligible_for_deletion"]["all"] = all_old_response.get("count", 0)

	return stats

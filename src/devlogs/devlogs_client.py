# Devlogs client for emitting logs to the collector
#
# This module provides utilities for applications to emit logs
# in the Devlogs format to a collector endpoint.

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class DevlogsClient:
    """Client for sending logs to a devlogs collector.

    Usage:
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="my-app",
            component="api-server",
        )

        # Send a single log
        client.emit(
            level="info",
            message="Request processed",
            fields={"user_id": "123", "duration_ms": 45}
        )

        # Send a batch
        client.emit_batch([
            {"message": "Event 1", "level": "info"},
            {"message": "Event 2", "level": "warning"},
        ])
    """

    collector_url: str
    application: str
    component: str
    environment: Optional[str] = None
    version: Optional[str] = None
    auth_token: Optional[str] = None
    timeout: int = 30

    def _get_endpoint(self) -> str:
        """Get the collector endpoint URL."""
        base = self.collector_url.rstrip("/")
        return f"{base}/v1/logs"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _now(self) -> str:
        """Get current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _build_record(
        self,
        message: Optional[str] = None,
        level: Optional[str] = None,
        area: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        **extra,
    ) -> Dict[str, Any]:
        """Build a Devlogs record.

        Args:
            message: Log message (top-level field)
            level: Log level (top-level field)
            area: Functional area (top-level field)
            fields: Additional custom fields
            timestamp: Override timestamp (default: now)
            **extra: Additional fields to merge into fields

        Returns:
            Devlogs record dict
        """
        record = {
            "application": self.application,
            "component": self.component,
            "timestamp": timestamp or self._now(),
        }

        # Top-level optional fields
        if message:
            record["message"] = message
        if level:
            record["level"] = level
        if area:
            record["area"] = area
        if self.environment:
            record["environment"] = self.environment
        if self.version:
            record["version"] = self.version

        # Build custom fields object
        record_fields = {}
        if fields:
            record_fields.update(fields)
        if extra:
            record_fields.update(extra)

        if record_fields:
            record["fields"] = record_fields

        return record

    def emit(
        self,
        message: Optional[str] = None,
        level: str = "info",
        area: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        **extra,
    ) -> bool:
        """Emit a single log record.

        Args:
            message: Log message
            level: Log level (debug, info, warning, error, critical)
            area: Functional area or category
            fields: Custom fields dict
            timestamp: Override timestamp
            **extra: Additional fields

        Returns:
            True if accepted, False on error
        """
        record = self._build_record(
            message=message,
            level=level,
            area=area,
            fields=fields,
            timestamp=timestamp,
            **extra,
        )
        return self._send([record])

    def emit_batch(
        self,
        records: List[Dict[str, Any]],
    ) -> bool:
        """Emit a batch of log records.

        Each record in the list should have at minimum a 'message' key.
        The application, component, and other client defaults are
        automatically added.

        Args:
            records: List of record dicts with optional keys:
                - message: Log message
                - level: Log level
                - fields: Custom fields
                - emitted_ts: Override timestamp

        Returns:
            True if accepted, False on error
        """
        built_records = [
            self._build_record(**r) for r in records
        ]
        return self._send(built_records)

    def _send(self, records: List[Dict[str, Any]]) -> bool:
        """Send records to the collector.

        Args:
            records: List of Devlogs record dicts

        Returns:
            True if accepted (202), False otherwise
        """
        if len(records) == 1:
            payload = records[0]
        else:
            payload = {"records": records}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._get_endpoint(),
            data=data,
            headers=self._get_headers(),
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 202
        except urllib.error.HTTPError as e:
            # Log error but don't raise - this is fire-and-forget
            return False
        except Exception:
            return False


def create_client(
    collector_url: str,
    application: str,
    component: str,
    environment: Optional[str] = None,
    version: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> DevlogsClient:
    """Create an Devlogs client.

    Args:
        collector_url: The collector endpoint URL (DEVLOGS_URL)
        application: Application name
        component: Component name within the application
        environment: Deployment environment (optional)
        version: Application version (optional)
        auth_token: Bearer token for authentication (optional)

    Returns:
        Configured DevlogsClient instance
    """
    return DevlogsClient(
        collector_url=collector_url,
        application=application,
        component=component,
        environment=environment,
        version=version,
        auth_token=auth_token,
    )


def emit_log(
    collector_url: str,
    application: str,
    component: str,
    message: str,
    level: str = "info",
    fields: Optional[Dict[str, Any]] = None,
    environment: Optional[str] = None,
    version: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> bool:
    """One-shot convenience function to emit a single log.

    For repeated logging, use create_client() instead.

    Args:
        collector_url: The collector endpoint URL
        application: Application name
        component: Component name
        message: Log message
        level: Log level
        fields: Custom fields
        environment: Deployment environment
        version: Application version
        auth_token: Bearer token

    Returns:
        True if accepted, False on error
    """
    client = create_client(
        collector_url=collector_url,
        application=application,
        component=component,
        environment=environment,
        version=version,
        auth_token=auth_token,
    )
    return client.emit(message=message, level=level, fields=fields)

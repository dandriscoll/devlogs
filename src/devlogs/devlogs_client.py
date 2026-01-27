# Devlogs client for emitting logs to the collector
#
# This module provides utilities for applications to emit logs
# in the Devlogs format to a collector endpoint.

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, unquote, urlunparse


def _parse_collector_url(url: str) -> Tuple[str, Optional[str]]:
    """Parse a URL and extract auth token if it's a collector URL.

    Distinguishes between OpenSearch URLs and collector URLs:
    - OpenSearch URL: has BOTH username AND password - keep credentials in URL
    - Collector URL: has only token in username position - extract for Bearer auth

    Collector URL format: http://token@host:port
    OpenSearch URL format: http://user:password@host:port

    Args:
        url: The URL, optionally with credentials in userinfo

    Returns:
        Tuple of (url, token):
        - For OpenSearch URLs (user:pass): returns original URL, None
        - For collector URLs (token only): returns clean URL without userinfo, token
        - For plain URLs: returns original URL, None
    """
    if not url:
        return url, None

    parsed = urlparse(url)

    # If no userinfo, return as-is
    if not parsed.username and not parsed.password:
        return url, None

    # OpenSearch URL: has BOTH username AND password
    # Keep the URL as-is with credentials, no Bearer token
    if parsed.username and parsed.password:
        return url, None

    # Collector URL: token in username position only (no password)
    # Extract token and strip userinfo from URL
    token = unquote(parsed.username) if parsed.username else None

    # Rebuild URL without userinfo
    # netloc without userinfo is just host:port
    if parsed.port:
        netloc = f"{parsed.hostname}:{parsed.port}"
    else:
        netloc = parsed.hostname or ""

    clean_url = urlunparse((
        parsed.scheme,
        netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))

    return clean_url, token


@dataclass
class DevlogsClient:
    """Client for sending logs to a devlogs collector or OpenSearch.

    URL Types:
        This client distinguishes between collector URLs and OpenSearch URLs:

        Collector URL (token in username position):
            http://dl1_myapp_secret@localhost:8080
            - Token is extracted and sent as Bearer auth header
            - Userinfo is stripped from the request URL

        OpenSearch URL (both username AND password):
            https://admin:password@opensearch.example.com:9200
            - Credentials remain in the URL for HTTP Basic auth
            - No Bearer token is used

    Usage:
        # Collector URL with token:
        client = DevlogsClient(
            collector_url="http://dl1_myapp_secret@localhost:8080",
            application="my-app",
            component="api-server",
        )

        # OpenSearch URL with credentials:
        client = DevlogsClient(
            collector_url="https://admin:password@opensearch.example.com:9200",
            application="my-app",
            component="api-server",
        )

        # Or with explicit auth_token parameter:
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="my-app",
            component="api-server",
            auth_token="dl1_myapp_secret",
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

    If both URL token and auth_token parameter are provided, auth_token takes precedence.
    """

    collector_url: str
    application: str
    component: str
    environment: Optional[str] = None
    version: Optional[str] = None
    auth_token: Optional[str] = None
    timeout: int = 30

    # Internal fields set by __post_init__
    _clean_url: str = field(default="", init=False, repr=False)
    _resolved_token: Optional[str] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Parse collector URL and extract token if present."""
        clean_url, url_token = _parse_collector_url(self.collector_url)
        self._clean_url = clean_url
        # Explicit auth_token parameter takes precedence over URL token
        self._resolved_token = self.auth_token if self.auth_token else url_token

    def _get_endpoint(self) -> str:
        """Get the collector endpoint URL."""
        base = self._clean_url.rstrip("/")
        return f"{base}/v1/logs"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {"Content-Type": "application/json"}
        if self._resolved_token:
            headers["Authorization"] = f"Bearer {self._resolved_token}"
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
    """Create a Devlogs client.

    Args:
        collector_url: The endpoint URL. URL type is auto-detected:
            - Collector URL: http://token@host:port (token becomes Bearer auth)
            - OpenSearch URL: http://user:pass@host:port (credentials kept in URL)
        application: Application name
        component: Component name within the application
        environment: Deployment environment (optional)
        version: Application version (optional)
        auth_token: Bearer token for authentication (optional, overrides URL token)

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
        collector_url: The endpoint URL. URL type is auto-detected:
            - Collector URL: http://token@host:port (token becomes Bearer auth)
            - OpenSearch URL: http://user:pass@host:port (credentials kept in URL)
        application: Application name
        component: Component name
        message: Log message
        level: Log level
        fields: Custom fields
        environment: Deployment environment
        version: Application version
        auth_token: Bearer token (optional, overrides URL token)

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

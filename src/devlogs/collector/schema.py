# Devlogs schema definition and validation
#
# The Devlogs schema standardizes log record structure for ingestion.
#
# Required fields:
#   - application (string): The application name emitting the log
#   - component (string): The component/module within the application
#   - timestamp (string): ISO 8601 UTC timestamp when event occurred at source
#
# Optional standardized fields:
#   - message (string): Human-readable log message
#   - level (string): Log level (debug, info, warning, error, critical)
#   - area (string): Functional area or category
#   - environment (string): Deployment environment (e.g., "development", "staging", "production")
#   - version (string): Application version
#
# Collector-set fields (added during ingestion):
#   - collected_ts (string): ISO 8601 UTC timestamp when collector received the record
#   - client_ip (string): IP address of the submitting client
#   - identity (object): Identity information resolved from auth token
#     - mode: "anonymous" | "verified" | "passthrough"
#     - For verified: id, name (optional), type (optional), tags (optional)
#     - For passthrough: preserves original identity from payload
#
# Custom fields:
#   - fields (object): Arbitrary nested JSON object for application-specific data

import re
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

from .errors import ValidationError

if TYPE_CHECKING:
    from .auth import Identity

# ISO 8601 timestamp pattern (simplified validation)
# Accepts formats like: 2024-01-15T10:30:00Z, 2024-01-15T10:30:00.123Z, 2024-01-15T10:30:00+00:00
ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$"
)


@dataclass
class DevlogsRecord:
    """Represents a single log record in the Devlogs schema.

    This class holds both the required fields from the incoming payload
    and the enrichment fields added by the collector.

    Attributes:
        application: The application name emitting the log (required)
        component: The component/module within the application (required)
        timestamp: ISO 8601 UTC timestamp when event occurred (required)
        message: Human-readable log message (optional)
        level: Log level - debug, info, warning, error, critical (optional)
        area: Functional area or category (optional)
        environment: Deployment environment (optional)
        version: Application version (optional)
        fields: Arbitrary nested JSON for custom data (optional)
        collected_ts: Timestamp when collector received (set by collector)
        client_ip: Submitting client IP address (set by collector)
        identity: Identity information resolved from auth (set by collector)
    """

    # Required fields from payload
    application: str
    component: str
    timestamp: str

    # Optional standardized fields
    message: Optional[str] = None
    level: Optional[str] = None
    area: Optional[str] = None
    environment: Optional[str] = None
    version: Optional[str] = None

    # Custom fields (pass-through)
    fields: Optional[Dict[str, Any]] = None

    # Collector-set fields
    collected_ts: Optional[str] = None
    client_ip: Optional[str] = None
    # Identity is stored as a dict for serialization; use Identity.to_dict() when setting
    _identity: Optional[Dict[str, Any]] = dataclass_field(default=None, repr=False)

    @property
    def identity(self) -> Optional[Dict[str, Any]]:
        """Get the identity dict."""
        return self._identity

    @identity.setter
    def identity(self, value: Any) -> None:
        """Set identity from dict or Identity object."""
        if value is None:
            self._identity = None
        elif isinstance(value, dict):
            self._identity = value
        elif hasattr(value, 'to_dict'):
            self._identity = value.to_dict()
        else:
            self._identity = value

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for indexing."""
        doc = {
            "application": self.application,
            "component": self.component,
            "timestamp": self.timestamp,
            "collected_ts": self.collected_ts,
            "client_ip": self.client_ip,
        }
        # Identity is always included (anonymous mode if not set)
        if self._identity is not None:
            doc["identity"] = self._identity
        else:
            doc["identity"] = {"mode": "anonymous"}
        if self.message is not None:
            doc["message"] = self.message
        if self.level is not None:
            doc["level"] = self.level
        if self.area is not None:
            doc["area"] = self.area
        if self.environment is not None:
            doc["environment"] = self.environment
        if self.version is not None:
            doc["version"] = self.version
        if self.fields is not None:
            doc["fields"] = self.fields
        return doc


def validate_timestamp(value: Any, field_name: str) -> str:
    """Validate that a value is a valid ISO 8601 timestamp.

    Args:
        value: The value to validate
        field_name: Name of the field for error messages

    Returns:
        The validated timestamp string

    Raises:
        ValidationError: If timestamp is missing or invalid format
    """
    if value is None:
        raise ValidationError(
            "MISSING_FIELD",
            f"Missing required field: {field_name}"
        )
    if not isinstance(value, str):
        raise ValidationError(
            "INVALID_TYPE",
            f"Field '{field_name}' must be a string, got {type(value).__name__}"
        )
    if not ISO8601_PATTERN.match(value):
        raise ValidationError(
            "INVALID_TIMESTAMP",
            f"Field '{field_name}' must be ISO 8601 format (e.g., 2024-01-15T10:30:00Z), got: {value}"
        )
    return value


def validate_string(value: Any, field_name: str, required: bool = True) -> Optional[str]:
    """Validate that a value is a non-empty string.

    Args:
        value: The value to validate
        field_name: Name of the field for error messages
        required: Whether the field is required

    Returns:
        The validated string, or None if optional and not provided

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        if required:
            raise ValidationError(
                "MISSING_FIELD",
                f"Missing required field: {field_name}"
            )
        return None
    if not isinstance(value, str):
        raise ValidationError(
            "INVALID_TYPE",
            f"Field '{field_name}' must be a string, got {type(value).__name__}"
        )
    value = value.strip()
    if required and not value:
        raise ValidationError(
            "EMPTY_FIELD",
            f"Field '{field_name}' cannot be empty"
        )
    return value if value else None


def validate_fields(value: Any) -> Optional[Dict[str, Any]]:
    """Validate that 'fields' is a valid nested object.

    Args:
        value: The value to validate

    Returns:
        The validated fields dict, or None if not provided

    Raises:
        ValidationError: If fields is not a dict
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValidationError(
            "INVALID_TYPE",
            f"Field 'fields' must be an object, got {type(value).__name__}"
        )
    return value


def validate_record(data: Dict[str, Any]) -> DevlogsRecord:
    """Validate a single log record against the Devlogs schema.

    Args:
        data: Dictionary containing the log record data

    Returns:
        DevlogsRecord with validated data

    Raises:
        ValidationError: If required fields are missing or invalid
    """
    if not isinstance(data, dict):
        raise ValidationError(
            "INVALID_PAYLOAD",
            f"Record must be an object, got {type(data).__name__}"
        )

    # Validate required fields
    application = validate_string(data.get("application"), "application", required=True)
    component = validate_string(data.get("component"), "component", required=True)
    timestamp = validate_timestamp(data.get("timestamp"), "timestamp")

    # Validate optional standardized fields
    message = validate_string(data.get("message"), "message", required=False)
    level = validate_string(data.get("level"), "level", required=False)
    area = validate_string(data.get("area"), "area", required=False)
    environment = validate_string(data.get("environment"), "environment", required=False)
    version = validate_string(data.get("version"), "version", required=False)

    # Validate custom fields
    fields = validate_fields(data.get("fields"))

    return DevlogsRecord(
        application=application,
        component=component,
        timestamp=timestamp,
        message=message,
        level=level,
        area=area,
        environment=environment,
        version=version,
        fields=fields,
    )


def normalize_records(payload: Any) -> List[Dict[str, Any]]:
    """Normalize a payload into a list of record dictionaries.

    Accepts either:
    - A single record object
    - A batch: {"records": [...]}

    Args:
        payload: The parsed JSON payload

    Returns:
        List of record dictionaries (not yet validated)

    Raises:
        ValidationError: If payload format is invalid
    """
    if payload is None:
        raise ValidationError(
            "INVALID_PAYLOAD",
            "Payload cannot be empty"
        )

    if not isinstance(payload, dict):
        raise ValidationError(
            "INVALID_PAYLOAD",
            f"Payload must be a JSON object, got {type(payload).__name__}"
        )

    # Check for batch format
    if "records" in payload:
        records = payload["records"]
        if not isinstance(records, list):
            raise ValidationError(
                "INVALID_PAYLOAD",
                f"'records' must be an array, got {type(records).__name__}"
            )
        if not records:
            raise ValidationError(
                "INVALID_PAYLOAD",
                "'records' array cannot be empty"
            )
        return records

    # Single record format
    return [payload]


def get_current_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def enrich_record(
    record: DevlogsRecord,
    client_ip: str,
    identity: Any,
) -> DevlogsRecord:
    """Enrich a record with collector metadata.

    Args:
        record: The validated record
        client_ip: IP address of the submitting client
        identity: Identity object or dict from auth resolution

    Returns:
        The enriched record
    """
    record.collected_ts = get_current_timestamp()
    record.client_ip = client_ip
    record.identity = identity
    return record

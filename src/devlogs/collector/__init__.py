# Collector module for devlogs
# Provides HTTP log ingestion with forward and ingest modes

from .schema import (
    DevlogsRecord,
    validate_record,
    normalize_records,
    enrich_record,
    get_current_timestamp,
)
from .errors import (
    CollectorError,
    ValidationError,
    ForwardError,
    IngestError,
    ConfigurationError,
    error_response,
    map_upstream_error,
    ERROR_VALIDATION_FAILED,
    ERROR_MISSING_REQUIRED_FIELD,
    ERROR_INVALID_TIMESTAMP,
    ERROR_INVALID_PAYLOAD,
    ERROR_FORWARD_FAILED,
    ERROR_INGEST_FAILED,
    ERROR_NOT_CONFIGURED,
)

__all__ = [
    "DevlogsRecord",
    "validate_record",
    "normalize_records",
    "enrich_record",
    "get_current_timestamp",
    "ValidationError",
    "ForwardError",
    "IngestError",
    "ConfigurationError",
    "CollectorError",
    "error_response",
    "map_upstream_error",
    "ERROR_VALIDATION_FAILED",
    "ERROR_MISSING_REQUIRED_FIELD",
    "ERROR_INVALID_TIMESTAMP",
    "ERROR_INVALID_PAYLOAD",
    "ERROR_FORWARD_FAILED",
    "ERROR_INGEST_FAILED",
    "ERROR_NOT_CONFIGURED",
]

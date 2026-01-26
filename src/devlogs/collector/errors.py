# Structured error handling for the collector

from typing import Dict, Any, Optional

# Error codes for structured responses
ERROR_VALIDATION_FAILED = "VALIDATION_FAILED"
ERROR_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
ERROR_INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
ERROR_INVALID_PAYLOAD = "INVALID_PAYLOAD"
ERROR_FORWARD_FAILED = "FORWARD_FAILED"
ERROR_INGEST_FAILED = "INGEST_FAILED"
ERROR_NOT_CONFIGURED = "NOT_CONFIGURED"
ERROR_RATE_LIMITED = "RATE_LIMITED"
ERROR_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"


class CollectorError(Exception):
    """Base exception for collector errors with structured response support."""

    def __init__(
        self,
        code: str,
        subcode: str,
        message: str,
        status_code: int = 400,
    ):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> Dict[str, str]:
        """Convert to structured error response format."""
        return {
            "code": self.code,
            "subcode": self.subcode,
            "message": self.message,
        }


class ValidationError(CollectorError):
    """Raised when payload validation fails."""

    def __init__(self, subcode: str, message: str):
        super().__init__(
            code=ERROR_VALIDATION_FAILED,
            subcode=subcode,
            message=message,
            status_code=400,
        )


class ForwardError(CollectorError):
    """Raised when forwarding to upstream fails."""

    def __init__(self, subcode: str, message: str, status_code: int = 502):
        super().__init__(
            code=ERROR_FORWARD_FAILED,
            subcode=subcode,
            message=message,
            status_code=status_code,
        )


class IngestError(CollectorError):
    """Raised when ingesting to OpenSearch fails."""

    def __init__(self, subcode: str, message: str, status_code: int = 500):
        super().__init__(
            code=ERROR_INGEST_FAILED,
            subcode=subcode,
            message=message,
            status_code=status_code,
        )


class ConfigurationError(CollectorError):
    """Raised when collector is not properly configured."""

    def __init__(self, message: str):
        super().__init__(
            code=ERROR_NOT_CONFIGURED,
            subcode="MISSING_CONFIG",
            message=message,
            status_code=503,
        )


def error_response(
    code: str,
    subcode: str,
    message: str,
) -> Dict[str, str]:
    """Create a structured error response dictionary.

    All error responses follow the format:
    {
        "code": "...",
        "subcode": "...",
        "message": "..."
    }

    Args:
        code: High-level error category (e.g., VALIDATION_FAILED)
        subcode: Specific error type within category (e.g., MISSING_FIELD)
        message: Human-readable error description

    Returns:
        Dictionary with code, subcode, and message keys
    """
    return {
        "code": code,
        "subcode": subcode,
        "message": message,
    }


def map_upstream_error(status_code: int, body: Optional[str] = None) -> CollectorError:
    """Map an upstream error response to a CollectorError.

    Used in forward mode to translate downstream errors.

    Args:
        status_code: HTTP status code from upstream
        body: Optional response body from upstream

    Returns:
        ForwardError with appropriate subcode
    """
    if status_code == 401:
        return ForwardError("UPSTREAM_UNAUTHORIZED", f"Upstream authentication failed: {body or 'No details'}")
    elif status_code == 403:
        return ForwardError("UPSTREAM_FORBIDDEN", f"Upstream access denied: {body or 'No details'}")
    elif status_code == 404:
        return ForwardError("UPSTREAM_NOT_FOUND", f"Upstream endpoint not found: {body or 'No details'}")
    elif status_code == 429:
        return ForwardError("UPSTREAM_RATE_LIMITED", f"Upstream rate limited: {body or 'No details'}", status_code=429)
    elif 400 <= status_code < 500:
        return ForwardError("UPSTREAM_CLIENT_ERROR", f"Upstream client error ({status_code}): {body or 'No details'}", status_code=400)
    elif 500 <= status_code < 600:
        return ForwardError("UPSTREAM_SERVER_ERROR", f"Upstream server error ({status_code}): {body or 'No details'}", status_code=502)
    else:
        return ForwardError("UPSTREAM_ERROR", f"Upstream error ({status_code}): {body or 'No details'}", status_code=502)

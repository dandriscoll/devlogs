# Forwarding logic for the collector
#
# When DEVLOGS_FORWARD_URL is set, the collector operates in forward mode:
# it proxies incoming requests to the configured upstream URL.

import json
import urllib.request
import urllib.error
from typing import Dict, Optional, Tuple, Any

from .errors import ForwardError, map_upstream_error


def forward_request(
    forward_url: str,
    body: bytes,
    content_type: str,
    auth_header: Optional[str] = None,
    request_id: Optional[str] = None,
    timeout: int = 30,
) -> Tuple[int, Dict[str, Any]]:
    """Forward a request to the upstream collector.

    Forwards the request body as-is, preserving relevant headers.

    Args:
        forward_url: The upstream URL to forward to (should end with /v1/logs)
        body: The raw request body bytes
        content_type: The Content-Type header value
        auth_header: Optional Authorization header to forward
        request_id: Optional X-Request-ID header to forward
        timeout: Request timeout in seconds

    Returns:
        Tuple of (status_code, response_body_dict)

    Raises:
        ForwardError: If the forward request fails
    """
    # Ensure URL ends with /v1/logs
    if not forward_url.endswith("/v1/logs"):
        forward_url = forward_url.rstrip("/") + "/v1/logs"

    headers = {
        "Content-Type": content_type,
    }
    if auth_header:
        headers["Authorization"] = auth_header
    if request_id:
        headers["X-Request-ID"] = request_id

    req = urllib.request.Request(
        forward_url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            try:
                response_body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                response_body = {"raw": raw}
            return status, response_body

    except urllib.error.HTTPError as e:
        # Read error body if available
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            error_body = None
        raise map_upstream_error(e.code, error_body)

    except urllib.error.URLError as e:
        reason = str(e.reason) if e.reason else "Unknown error"
        raise ForwardError(
            "CONNECTION_FAILED",
            f"Failed to connect to upstream: {reason}",
            status_code=502,
        )

    except TimeoutError:
        raise ForwardError(
            "TIMEOUT",
            f"Upstream request timed out after {timeout}s",
            status_code=504,
        )

    except Exception as e:
        raise ForwardError(
            "UNEXPECTED_ERROR",
            f"Unexpected error during forward: {str(e)}",
            status_code=502,
        )

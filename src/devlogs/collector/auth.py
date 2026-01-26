# Token validation and identity resolution for the collector
#
# This module handles:
# - Token format validation (dl1_<kid>_<secret>)
# - Auth header parsing (Devlogs1, Bearer, X-Devlogs-Token)
# - Token-to-identity mapping
# - Identity resolution based on auth mode

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote

# Token format: dl1_<kid>_<secret>
# - kid: 6-24 alphanumeric + underscore/hyphen characters
# - secret: 32-64 alphanumeric + underscore/hyphen characters
TOKEN_PATTERN = re.compile(r"^dl1_[A-Za-z0-9_-]{6,24}_[A-Za-z0-9_-]{32,64}$")

# Auth header patterns
DEVLOGS1_PATTERN = re.compile(r"^Devlogs1\s+(\S+)", re.IGNORECASE)
BEARER_PATTERN = re.compile(r"^Bearer\s+(\S+)", re.IGNORECASE)

# Auth modes
AUTH_MODE_ALLOW_ANONYMOUS = "allow_anonymous"
AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH = "require_token_passthrough"
AUTH_MODE_REQUIRE_TOKEN_VERIFIED = "require_token_verified"

VALID_AUTH_MODES = (
    AUTH_MODE_ALLOW_ANONYMOUS,
    AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH,
    AUTH_MODE_REQUIRE_TOKEN_VERIFIED,
)


@dataclass
class Identity:
    """Represents an identity attached to a log record.

    Three modes:
    - anonymous: No verified identity
    - verified: Token was mapped to a known identity
    - passthrough: Identity from payload preserved as-is
    """
    mode: str
    id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    # For passthrough mode, store the original identity object
    _passthrough_data: Optional[Dict[str, Any]] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert identity to dictionary for indexing."""
        if self.mode == "passthrough" and self._passthrough_data:
            # Return the original passthrough data with mode set
            result = {"mode": "passthrough"}
            result.update(self._passthrough_data)
            return result

        result = {"mode": self.mode}
        if self.mode == "verified":
            if self.id is not None:
                result["id"] = self.id
            if self.name is not None:
                result["name"] = self.name
            if self.type is not None:
                result["type"] = self.type
            if self.tags:
                result["tags"] = self.tags
        return result

    @staticmethod
    def anonymous() -> "Identity":
        """Create an anonymous identity."""
        return Identity(mode="anonymous")

    @staticmethod
    def verified(id: str, name: Optional[str] = None, type: Optional[str] = None,
                 tags: Optional[Dict[str, str]] = None) -> "Identity":
        """Create a verified identity from token mapping."""
        return Identity(mode="verified", id=id, name=name, type=type, tags=tags)

    @staticmethod
    def passthrough(data: Dict[str, Any]) -> "Identity":
        """Create a passthrough identity from payload data."""
        return Identity(mode="passthrough", _passthrough_data=data)


@dataclass
class TokenMapping:
    """Represents a token-to-identity mapping entry."""
    token: str
    id: str
    name: Optional[str] = None
    type: Optional[str] = None
    tags: Optional[Dict[str, str]] = None

    def to_identity(self) -> Identity:
        """Convert this mapping to a verified Identity."""
        return Identity.verified(
            id=self.id,
            name=self.name,
            type=self.type,
            tags=self.tags,
        )


def is_token_well_formed(token: Optional[str]) -> bool:
    """Check if a token matches the dl1_<kid>_<secret> format.

    Args:
        token: The token string (without auth scheme prefix)

    Returns:
        True if the token matches the required format
    """
    if not token:
        return False
    return bool(TOKEN_PATTERN.match(token))


def extract_token_from_headers(
    authorization: Optional[str] = None,
    x_devlogs_token: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """Extract token from request headers with proper precedence.

    Precedence: Devlogs1 → Bearer → X-Devlogs-Token

    Args:
        authorization: The Authorization header value
        x_devlogs_token: The X-Devlogs-Token header value

    Returns:
        Tuple of (token_value, source) where source is one of:
        'devlogs1', 'bearer', 'x-devlogs-token', or 'none'
    """
    if authorization:
        authorization = authorization.strip()

        # Try Devlogs1 first
        match = DEVLOGS1_PATTERN.match(authorization)
        if match:
            return match.group(1), "devlogs1"

        # Try Bearer
        match = BEARER_PATTERN.match(authorization)
        if match:
            return match.group(1), "bearer"

    # Fall back to X-Devlogs-Token
    if x_devlogs_token:
        token = x_devlogs_token.strip()
        if token:
            return token, "x-devlogs-token"

    return None, "none"


def parse_token_map_kv(kv_string: Optional[str]) -> Dict[str, TokenMapping]:
    """Parse the DEVLOGS_TOKEN_MAP_KV environment variable.

    Format: <token>=<id>[,<name>][,<type>][,<tags>];<token>=...
    Tags format: k1:v1|k2:v2
    Percent-encoding required for reserved chars: %;=,|:%

    Args:
        kv_string: The raw KV string from environment

    Returns:
        Dict mapping token strings to TokenMapping objects
    """
    if not kv_string:
        return {}

    result = {}

    # Split on semicolon for entries
    entries = kv_string.split(";")

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        # Skip comments
        if entry.startswith("#"):
            continue

        # Split on first = to get token and value
        eq_pos = entry.find("=")
        if eq_pos == -1:
            continue

        token = entry[:eq_pos].strip()
        value = entry[eq_pos + 1:].strip()

        if not token or not value:
            continue

        # Token is NOT percent-decoded
        if not is_token_well_formed(token):
            continue

        # Parse value: id,name,type,tags
        parts = value.split(",", 3)  # Max 4 parts

        # id is required
        id_val = unquote(parts[0].strip()) if parts else ""
        if not id_val:
            continue

        name_val = unquote(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else None
        type_val = unquote(parts[2].strip()) if len(parts) > 2 and parts[2].strip() else None
        tags_val = None

        if len(parts) > 3 and parts[3].strip():
            tags_str = parts[3].strip()
            tags_val = _parse_tags(tags_str)

        result[token] = TokenMapping(
            token=token,
            id=id_val,
            name=name_val,
            type=type_val,
            tags=tags_val,
        )

    return result


def _parse_tags(tags_str: str) -> Optional[Dict[str, str]]:
    """Parse tags from k1:v1|k2:v2 format.

    Args:
        tags_str: The tags string

    Returns:
        Dict of tag key-value pairs, or None if empty
    """
    if not tags_str:
        return None

    tags = {}
    pairs = tags_str.split("|")

    for pair in pairs:
        pair = pair.strip()
        if not pair:
            continue

        colon_pos = pair.find(":")
        if colon_pos == -1:
            continue

        key = unquote(pair[:colon_pos].strip())
        val = unquote(pair[colon_pos + 1:].strip())

        if key:  # Allow empty values
            tags[key] = val

    return tags if tags else None


class AuthError(Exception):
    """Raised when authentication fails."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_forward_index_map_kv(kv_string: Optional[str]) -> Dict[str, str]:
    """Parse the DEVLOGS_FORWARD_INDEX_MAP_KV environment variable.

    Format: <application>=<index>;<application>=...

    Args:
        kv_string: The raw KV string from environment

    Returns:
        Dict mapping application names to index names
    """
    if not kv_string:
        return {}

    result = {}

    # Split on semicolon for entries
    entries = kv_string.split(";")

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        # Skip comments
        if entry.startswith("#"):
            continue

        # Split on first = to get application and index
        eq_pos = entry.find("=")
        if eq_pos == -1:
            continue

        application = entry[:eq_pos].strip()
        index = entry[eq_pos + 1:].strip()

        if application and index:
            result[application] = index

    return result


def resolve_identity(
    auth_mode: str,
    token: Optional[str],
    token_map: Dict[str, TokenMapping],
    payload_identity: Optional[Dict[str, Any]] = None,
) -> Identity:
    """Resolve the identity for a request based on auth mode.

    Args:
        auth_mode: One of allow_anonymous, require_token_passthrough, require_token_verified
        token: The extracted token (may be None)
        token_map: Dict of token -> TokenMapping
        payload_identity: The identity object from the payload (if any)

    Returns:
        The resolved Identity

    Raises:
        AuthError: If authentication requirements not met
    """
    if auth_mode == AUTH_MODE_ALLOW_ANONYMOUS:
        # Token optional
        # If token is verified via mapping → verified identity
        # Otherwise → anonymous
        if token and is_token_well_formed(token):
            mapping = token_map.get(token)
            if mapping:
                return mapping.to_identity()
        return Identity.anonymous()

    elif auth_mode == AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH:
        # Token must be present (reject if missing)
        if not token:
            raise AuthError("AUTH_REQUIRED", "Authentication token required")

        # Token is not verified - we don't check the map
        # If payload includes identity, preserve it exactly
        if payload_identity and isinstance(payload_identity, dict):
            return Identity.passthrough(payload_identity)
        # If payload lacks identity, set anonymous
        return Identity.anonymous()

    elif auth_mode == AUTH_MODE_REQUIRE_TOKEN_VERIFIED:
        # Token must be present, properly formed, and in mapping
        if not token:
            raise AuthError("AUTH_REQUIRED", "Authentication token required")

        if not is_token_well_formed(token):
            raise AuthError("INVALID_TOKEN", "Token format invalid")

        mapping = token_map.get(token)
        if not mapping:
            raise AuthError("TOKEN_NOT_FOUND", "Token not recognized")

        return mapping.to_identity()

    else:
        # Unknown auth mode - default to anonymous
        return Identity.anonymous()

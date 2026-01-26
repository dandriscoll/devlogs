# Tests for collector authentication and identity resolution

import pytest
from devlogs.collector.auth import (
    Identity,
    TokenMapping,
    is_token_well_formed,
    extract_token_from_headers,
    parse_token_map_kv,
    parse_forward_index_map_kv,
    resolve_identity,
    AuthError,
    AUTH_MODE_ALLOW_ANONYMOUS,
    AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH,
    AUTH_MODE_REQUIRE_TOKEN_VERIFIED,
)


class TestIdentity:
    """Tests for the Identity dataclass."""

    def test_anonymous_identity(self):
        identity = Identity.anonymous()
        assert identity.mode == "anonymous"
        assert identity.id is None
        assert identity.name is None
        assert identity.to_dict() == {"mode": "anonymous"}

    def test_verified_identity_minimal(self):
        identity = Identity.verified(id="user-123")
        assert identity.mode == "verified"
        assert identity.id == "user-123"
        assert identity.name is None
        d = identity.to_dict()
        assert d["mode"] == "verified"
        assert d["id"] == "user-123"
        assert "name" not in d

    def test_verified_identity_full(self):
        identity = Identity.verified(
            id="user-123",
            name="Test User",
            type="service",
            tags={"team": "platform", "env": "prod"}
        )
        d = identity.to_dict()
        assert d["mode"] == "verified"
        assert d["id"] == "user-123"
        assert d["name"] == "Test User"
        assert d["type"] == "service"
        assert d["tags"] == {"team": "platform", "env": "prod"}

    def test_passthrough_identity(self):
        payload_identity = {"custom_id": "abc", "role": "admin"}
        identity = Identity.passthrough(payload_identity)
        assert identity.mode == "passthrough"
        d = identity.to_dict()
        assert d["mode"] == "passthrough"
        assert d["custom_id"] == "abc"
        assert d["role"] == "admin"


class TestTokenMapping:
    """Tests for the TokenMapping dataclass."""

    def test_to_identity(self):
        mapping = TokenMapping(
            token="dl1_mykey1_12345678901234567890123456789012",
            id="service-1",
            name="My Service",
            type="service",
            tags={"team": "backend"}
        )
        identity = mapping.to_identity()
        assert identity.mode == "verified"
        assert identity.id == "service-1"
        assert identity.name == "My Service"
        assert identity.type == "service"
        assert identity.tags == {"team": "backend"}


class TestIsTokenWellFormed:
    """Tests for token format validation (dl1_<kid>_<secret> format)."""

    def test_valid_token_minimal_lengths(self):
        # kid: 6 chars, secret: 32 chars
        token = "dl1_abc123_12345678901234567890123456789012"
        assert is_token_well_formed(token) is True

    def test_valid_token_max_lengths(self):
        # kid: 24 chars, secret: 64 chars
        kid = "a" * 24
        secret = "b" * 64
        token = f"dl1_{kid}_{secret}"
        assert is_token_well_formed(token) is True

    def test_valid_token_with_special_chars(self):
        # Underscore and hyphen allowed in kid and secret
        token = "dl1_my-key_1_1234567890123456789012345678901a-b"
        assert is_token_well_formed(token) is True

    def test_empty_returns_false(self):
        assert is_token_well_formed(None) is False
        assert is_token_well_formed("") is False
        assert is_token_well_formed("   ") is False

    def test_wrong_prefix_returns_false(self):
        assert is_token_well_formed("dl2_abc123_12345678901234567890123456789012") is False
        assert is_token_well_formed("abc_abc123_12345678901234567890123456789012") is False

    def test_kid_too_short_returns_false(self):
        # kid: 5 chars (min is 6)
        token = "dl1_abc12_12345678901234567890123456789012"
        assert is_token_well_formed(token) is False

    def test_kid_too_long_returns_false(self):
        # kid: 25 chars (max is 24)
        kid = "a" * 25
        token = f"dl1_{kid}_12345678901234567890123456789012"
        assert is_token_well_formed(token) is False

    def test_secret_too_short_returns_false(self):
        # secret: 31 chars (min is 32)
        token = "dl1_abc123_1234567890123456789012345678901"
        assert is_token_well_formed(token) is False

    def test_secret_too_long_returns_false(self):
        # secret: 65 chars (max is 64)
        secret = "a" * 65
        token = f"dl1_abc123_{secret}"
        assert is_token_well_formed(token) is False

    def test_bearer_prefix_not_stripped(self):
        # Token should NOT have Bearer prefix
        token = "Bearer dl1_abc123_12345678901234567890123456789012"
        assert is_token_well_formed(token) is False

    def test_jwt_format_returns_false(self):
        # JWT format is not valid for dl1 tokens
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"
        assert is_token_well_formed(jwt) is False


class TestExtractTokenFromHeaders:
    """Tests for token extraction from headers."""

    def test_devlogs1_takes_precedence(self):
        token, source = extract_token_from_headers(
            authorization="Devlogs1 dl1_abc123_12345678901234567890123456789012",
            x_devlogs_token="dl1_other1_12345678901234567890123456789012",
        )
        assert token == "dl1_abc123_12345678901234567890123456789012"
        assert source == "devlogs1"

    def test_bearer_second_precedence(self):
        token, source = extract_token_from_headers(
            authorization="Bearer dl1_abc123_12345678901234567890123456789012",
            x_devlogs_token="dl1_other1_12345678901234567890123456789012",
        )
        assert token == "dl1_abc123_12345678901234567890123456789012"
        assert source == "bearer"

    def test_x_devlogs_token_fallback(self):
        token, source = extract_token_from_headers(
            authorization=None,
            x_devlogs_token="dl1_abc123_12345678901234567890123456789012",
        )
        assert token == "dl1_abc123_12345678901234567890123456789012"
        assert source == "x-devlogs-token"

    def test_no_token(self):
        token, source = extract_token_from_headers(None, None)
        assert token is None
        assert source == "none"

    def test_devlogs1_case_insensitive(self):
        token, source = extract_token_from_headers(
            authorization="DEVLOGS1 mytoken",
            x_devlogs_token=None,
        )
        assert token == "mytoken"
        assert source == "devlogs1"

    def test_bearer_case_insensitive(self):
        token, source = extract_token_from_headers(
            authorization="BEARER mytoken",
            x_devlogs_token=None,
        )
        assert token == "mytoken"
        assert source == "bearer"

    def test_whitespace_handling(self):
        token, source = extract_token_from_headers(
            authorization="  Bearer   mytoken  ",
            x_devlogs_token=None,
        )
        assert token == "mytoken"


class TestParseTokenMapKV:
    """Tests for KV format parsing of token-to-identity mapping."""

    def test_single_entry_minimal(self):
        kv = "dl1_abc123_12345678901234567890123456789012=user-1"
        result = parse_token_map_kv(kv)
        assert len(result) == 1
        mapping = result["dl1_abc123_12345678901234567890123456789012"]
        assert mapping.id == "user-1"
        assert mapping.name is None
        assert mapping.type is None
        assert mapping.tags is None

    def test_single_entry_full(self):
        kv = "dl1_abc123_12345678901234567890123456789012=user-1,Test User,service,team:backend|env:prod"
        result = parse_token_map_kv(kv)
        mapping = result["dl1_abc123_12345678901234567890123456789012"]
        assert mapping.id == "user-1"
        assert mapping.name == "Test User"
        assert mapping.type == "service"
        assert mapping.tags == {"team": "backend", "env": "prod"}

    def test_multiple_entries(self):
        kv = (
            "dl1_key001_12345678901234567890123456789012=user-1,User One;"
            "dl1_key002_12345678901234567890123456789012=user-2,User Two"
        )
        result = parse_token_map_kv(kv)
        assert len(result) == 2
        assert result["dl1_key001_12345678901234567890123456789012"].id == "user-1"
        assert result["dl1_key002_12345678901234567890123456789012"].id == "user-2"

    def test_empty_string(self):
        assert parse_token_map_kv("") == {}
        assert parse_token_map_kv(None) == {}

    def test_skips_comments(self):
        kv = "# This is a comment;dl1_abc123_12345678901234567890123456789012=user-1"
        result = parse_token_map_kv(kv)
        assert len(result) == 1

    def test_skips_malformed_tokens(self):
        kv = "invalid-token=user-1;dl1_abc123_12345678901234567890123456789012=user-2"
        result = parse_token_map_kv(kv)
        assert len(result) == 1
        assert "dl1_abc123_12345678901234567890123456789012" in result

    def test_percent_encoding(self):
        # Name contains comma, must be percent-encoded
        kv = "dl1_abc123_12345678901234567890123456789012=user-1,Name%2C With Comma"
        result = parse_token_map_kv(kv)
        mapping = result["dl1_abc123_12345678901234567890123456789012"]
        assert mapping.name == "Name, With Comma"

    def test_skips_empty_entries(self):
        kv = ";;dl1_abc123_12345678901234567890123456789012=user-1;;"
        result = parse_token_map_kv(kv)
        assert len(result) == 1

    def test_whitespace_handling(self):
        kv = "  dl1_abc123_12345678901234567890123456789012 = user-1 , Test User  "
        result = parse_token_map_kv(kv)
        mapping = result["dl1_abc123_12345678901234567890123456789012"]
        assert mapping.id == "user-1"
        assert mapping.name == "Test User"


class TestResolveIdentity:
    """Tests for identity resolution based on auth mode."""

    @pytest.fixture
    def token_map(self):
        return {
            "dl1_valid1_12345678901234567890123456789012": TokenMapping(
                token="dl1_valid1_12345678901234567890123456789012",
                id="service-1",
                name="Test Service",
                type="service",
            )
        }

    # allow_anonymous mode tests

    def test_anonymous_mode_no_token(self, token_map):
        identity = resolve_identity(
            auth_mode=AUTH_MODE_ALLOW_ANONYMOUS,
            token=None,
            token_map=token_map,
        )
        assert identity.mode == "anonymous"

    def test_anonymous_mode_invalid_token(self, token_map):
        identity = resolve_identity(
            auth_mode=AUTH_MODE_ALLOW_ANONYMOUS,
            token="invalid",
            token_map=token_map,
        )
        assert identity.mode == "anonymous"

    def test_anonymous_mode_unknown_token(self, token_map):
        identity = resolve_identity(
            auth_mode=AUTH_MODE_ALLOW_ANONYMOUS,
            token="dl1_unknwn_12345678901234567890123456789012",
            token_map=token_map,
        )
        assert identity.mode == "anonymous"

    def test_anonymous_mode_valid_token(self, token_map):
        identity = resolve_identity(
            auth_mode=AUTH_MODE_ALLOW_ANONYMOUS,
            token="dl1_valid1_12345678901234567890123456789012",
            token_map=token_map,
        )
        assert identity.mode == "verified"
        assert identity.id == "service-1"

    # require_token_passthrough mode tests

    def test_passthrough_mode_no_token_raises(self, token_map):
        with pytest.raises(AuthError) as exc:
            resolve_identity(
                auth_mode=AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH,
                token=None,
                token_map=token_map,
            )
        assert exc.value.code == "AUTH_REQUIRED"

    def test_passthrough_mode_with_payload_identity(self, token_map):
        payload_identity = {"custom_id": "abc", "role": "admin"}
        identity = resolve_identity(
            auth_mode=AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH,
            token="any-token-value",  # Not validated in passthrough
            token_map=token_map,
            payload_identity=payload_identity,
        )
        assert identity.mode == "passthrough"
        d = identity.to_dict()
        assert d["custom_id"] == "abc"
        assert d["role"] == "admin"

    def test_passthrough_mode_without_payload_identity(self, token_map):
        identity = resolve_identity(
            auth_mode=AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH,
            token="any-token-value",
            token_map=token_map,
            payload_identity=None,
        )
        assert identity.mode == "anonymous"

    # require_token_verified mode tests

    def test_verified_mode_no_token_raises(self, token_map):
        with pytest.raises(AuthError) as exc:
            resolve_identity(
                auth_mode=AUTH_MODE_REQUIRE_TOKEN_VERIFIED,
                token=None,
                token_map=token_map,
            )
        assert exc.value.code == "AUTH_REQUIRED"

    def test_verified_mode_invalid_token_raises(self, token_map):
        with pytest.raises(AuthError) as exc:
            resolve_identity(
                auth_mode=AUTH_MODE_REQUIRE_TOKEN_VERIFIED,
                token="invalid-format",
                token_map=token_map,
            )
        assert exc.value.code == "INVALID_TOKEN"

    def test_verified_mode_unknown_token_raises(self, token_map):
        with pytest.raises(AuthError) as exc:
            resolve_identity(
                auth_mode=AUTH_MODE_REQUIRE_TOKEN_VERIFIED,
                token="dl1_unknwn_12345678901234567890123456789012",
                token_map=token_map,
            )
        assert exc.value.code == "TOKEN_NOT_FOUND"

    def test_verified_mode_valid_token(self, token_map):
        identity = resolve_identity(
            auth_mode=AUTH_MODE_REQUIRE_TOKEN_VERIFIED,
            token="dl1_valid1_12345678901234567890123456789012",
            token_map=token_map,
        )
        assert identity.mode == "verified"
        assert identity.id == "service-1"
        assert identity.name == "Test Service"
        assert identity.type == "service"

    # Unknown mode tests

    def test_unknown_mode_returns_anonymous(self, token_map):
        identity = resolve_identity(
            auth_mode="unknown_mode",
            token="dl1_valid1_12345678901234567890123456789012",
            token_map=token_map,
        )
        assert identity.mode == "anonymous"


class TestParseForwardIndexMapKV:
    """Tests for forward index map KV parsing."""

    def test_single_entry(self):
        kv = "app1=devlogs-app1"
        result = parse_forward_index_map_kv(kv)
        assert result == {"app1": "devlogs-app1"}

    def test_multiple_entries(self):
        kv = "app1=devlogs-app1;app2=devlogs-app2;app3=devlogs-app3"
        result = parse_forward_index_map_kv(kv)
        assert len(result) == 3
        assert result["app1"] == "devlogs-app1"
        assert result["app2"] == "devlogs-app2"
        assert result["app3"] == "devlogs-app3"

    def test_empty_string(self):
        assert parse_forward_index_map_kv("") == {}
        assert parse_forward_index_map_kv(None) == {}

    def test_skips_comments(self):
        kv = "# This is a comment;app1=devlogs-app1"
        result = parse_forward_index_map_kv(kv)
        assert len(result) == 1
        assert result["app1"] == "devlogs-app1"

    def test_skips_invalid_entries(self):
        kv = "invalid;app1=devlogs-app1;=nokey;novalue="
        result = parse_forward_index_map_kv(kv)
        assert len(result) == 1
        assert result["app1"] == "devlogs-app1"

    def test_whitespace_handling(self):
        kv = "  app1 = devlogs-app1 ; app2=devlogs-app2  "
        result = parse_forward_index_map_kv(kv)
        assert result["app1"] == "devlogs-app1"
        assert result["app2"] == "devlogs-app2"

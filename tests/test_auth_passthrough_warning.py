# Tests for DL-008: require_token_passthrough verifies the token but NOT identity.
# The fix is documentation + an in-code warning (no logic change). These tests guard
# that the warning text is present (so it cannot silently regress) and pin the current
# intentional contract that the payload identity is preserved verbatim.

import inspect
from pathlib import Path

from devlogs.collector.auth import (
    resolve_identity,
    AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_passthrough_branch_has_security_warning_in_source():
    src = inspect.getsource(resolve_identity)
    assert "SECURITY" in src
    assert "does NOT verify" in src


def test_howto_collector_doc_warns_about_passthrough_identity():
    doc = (REPO_ROOT / "HOWTO-COLLECTOR.md").read_text()
    assert "require_token_passthrough" in doc
    assert "does NOT verify" in doc


def test_passthrough_preserves_client_supplied_identity():
    # Documents the forgeability the warning describes: any well-formed token lets the
    # client set an arbitrary identity, preserved verbatim.
    ident = resolve_identity(
        AUTH_MODE_REQUIRE_TOKEN_PASSTHROUGH,
        token="any-token-value",
        token_map={},
        payload_identity={"id": "impersonated-service", "name": "victim"},
    )
    d = ident.to_dict()
    assert d["mode"] == "passthrough"
    assert d["id"] == "impersonated-service"

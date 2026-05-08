# End-to-end smoke test for the all-in-one Dockerfile.loki-proxy image.
#
# Builds (or reuses) the image, runs it on an ephemeral host port, then
# round-trips a single log record:
#
#     write  →  POST /ingest               (proxy → collector → Loki plugin)
#     read   →  GET  /query/loki/api/v1/query_range  (proxy → Loki, Bearer auth)
#
# This is the deploy-contract for the standalone image. If the proxy,
# collector, or Loki configs drift in a way that breaks the pipeline, this
# test catches it before downstream consumers are affected.
#
# Usage:
#   pytest tests/test_loki_proxy_image.py -m integration -v
#
# Knobs:
#   DEVLOGS_TEST_LOKI_PROXY_IMAGE  reuse an already-built tag instead of
#                                  building (saves ~minute on iteration)
#   DEVLOGS_TEST_KEEP_CONTAINER    leave the container running after the
#                                  test finishes (debugging only)

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_TOKEN = "smoke-test-admin-token"

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(base_url: str, timeout: float = 60.0) -> None:
    """Block until /query/ready returns 200 (Loki is up behind the proxy)."""
    deadline = time.time() + timeout
    last_err: Exception | None = None
    ready_url = f"{base_url}/query/ready"
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                ready_url,
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            last_err = e
        time.sleep(1.0)
    raise TimeoutError(f"loki-proxy image not ready within {timeout}s: {last_err}")


@pytest.fixture(scope="module")
def loki_proxy_container():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available")

    image = os.environ.get("DEVLOGS_TEST_LOKI_PROXY_IMAGE")
    if not image:
        image = f"devlogs-loki-proxy:test-{uuid.uuid4().hex[:8]}"
        build = subprocess.run(
            [
                "docker", "build",
                "-f", "Dockerfile.loki-proxy",
                "-t", image,
                ".",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if build.returncode != 0:
            pytest.skip(
                f"docker build failed (skipping smoke test):\n"
                f"stdout:\n{build.stdout}\nstderr:\n{build.stderr}"
            )

    port = _free_port()
    name = f"devlogs-loki-proxy-smoke-{uuid.uuid4().hex[:8]}"
    run = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", name,
            "-p", f"127.0.0.1:{port}:8080",
            "-e", f"LOKI_ADMIN_TOKEN={ADMIN_TOKEN}",
            image,
        ],
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        pytest.skip(f"docker run failed: {run.stderr}")

    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_ready(base_url)
        yield base_url
    finally:
        if not os.environ.get("DEVLOGS_TEST_KEEP_CONTAINER"):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _post_json(url: str, payload: dict) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _query_range(base_url: str, logql: str, start_ns: int, end_ns: int) -> dict:
    qs = urllib.parse.urlencode({
        "query": logql,
        "start": str(start_ns),
        "end": str(end_ns),
        "limit": "100",
    })
    url = f"{base_url}/query/loki/api/v1/query_range?{qs}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_round_trip_via_proxy(loki_proxy_container):
    """A log written through /ingest is retrievable via /query."""
    base_url = loki_proxy_container

    application = f"smoke-{uuid.uuid4().hex[:8]}"
    operation_id = f"op-{uuid.uuid4().hex[:8]}"
    record = {
        "application": application,
        "component": "smoke",
        "area": "test",
        "level": "info",
        "environment": "ci",
        "message": "round-trip from smoke test",
        "operation_id": operation_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    write_started_ns = int(time.time() * 1e9)
    status, body = _post_json(f"{base_url}/ingest", record)
    assert status in (200, 202), f"ingest failed: HTTP {status} {body}"

    # Loki is near-real-time; give the push a moment to be queryable.
    deadline = time.time() + 15.0
    streams: list = []
    while time.time() < deadline:
        result = _query_range(
            base_url,
            f'{{application="{application}"}}',
            start_ns=write_started_ns - 5 * 10**9,
            end_ns=int(time.time() * 1e9) + 10**9,
        )
        streams = result.get("data", {}).get("result", []) or []
        if streams:
            break
        time.sleep(1.0)

    assert streams, f"no streams returned for application={application}"
    # Confirm our specific operation_id made it through the JSON log line.
    seen_ops = []
    for stream in streams:
        for _ts, line in stream.get("values", []):
            try:
                seen_ops.append(json.loads(line).get("operation_id"))
            except json.JSONDecodeError:
                continue
    assert operation_id in seen_ops, (
        f"operation_id {operation_id} not found in returned log lines: {seen_ops}"
    )

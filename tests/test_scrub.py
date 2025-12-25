from datetime import datetime, timezone

from devlogs import scrub


class FakeClient:
    def __init__(self, deleted=0):
        self.deleted = deleted
        self.calls = []

    def delete_by_query(self, index, body, refresh=None, conflicts=None, slices=None):
        self.calls.append(
            {
                "index": index,
                "body": body,
                "refresh": refresh,
                "conflicts": conflicts,
                "slices": slices,
            }
        )
        return {"deleted": self.deleted}


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)


def _assert_cutoff(call_body, expected_iso):
    filters = call_body["query"]["bool"]["filter"]
    assert {"term": {"level": "debug"}} in filters
    assert {"range": {"timestamp": {"lt": expected_iso}}} in filters


def test_scrub_runtime_overrides_env(monkeypatch):
    monkeypatch.setenv("DEVLOGS_RETENTION_DEBUG_HOURS", "48")
    monkeypatch.setattr(scrub, "datetime", FixedDateTime)
    client = FakeClient(deleted=3)
    deleted = scrub.scrub_debug_logs(client, "devlogs-test", older_than_hours=12)
    assert deleted == 3
    assert len(client.calls) == 1
    _assert_cutoff(client.calls[0]["body"], "2025-01-01T12:00:00Z")


def test_scrub_env_overrides_default(monkeypatch):
    monkeypatch.setenv("DEVLOGS_RETENTION_DEBUG_HOURS", "36")
    monkeypatch.setattr(scrub, "datetime", FixedDateTime)
    client = FakeClient()
    scrub.scrub_debug_logs(client, "devlogs-test")
    assert len(client.calls) == 1
    _assert_cutoff(client.calls[0]["body"], "2024-12-31T12:00:00Z")


def test_scrub_defaults_to_24h(monkeypatch):
    monkeypatch.delenv("DEVLOGS_RETENTION_DEBUG_HOURS", raising=False)
    monkeypatch.setattr(scrub, "datetime", FixedDateTime)
    client = FakeClient()
    scrub.scrub_debug_logs(client, "devlogs-test")
    assert len(client.calls) == 1
    _assert_cutoff(client.calls[0]["body"], "2025-01-01T00:00:00Z")

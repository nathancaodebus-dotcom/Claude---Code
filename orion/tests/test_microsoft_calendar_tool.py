import pytest

from tools import microsoft_calendar_tool as cal


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json_data = json_data or {}
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def fake_token(monkeypatch):
    monkeypatch.setattr(cal, "get_access_token", lambda: "fake-token")


def test_list_events_no_upcoming(monkeypatch):
    monkeypatch.setattr(cal.client, "get", lambda *a, **kw: _FakeResponse({"value": []}))
    result = cal.ListOutlookEventsTool().run()
    assert result == "No upcoming events."


def test_list_events_formats_results(monkeypatch):
    events = {"value": [{"id": "e1", "subject": "Standup", "start": {"dateTime": "2026-08-12T09:00:00"}}]}
    monkeypatch.setattr(cal.client, "get", lambda *a, **kw: _FakeResponse(events))

    result = cal.ListOutlookEventsTool().run()

    assert "Standup" in result
    assert "e1" in result


def test_create_event_defaults_end_time(monkeypatch):
    """Regression test: Graph's dateTime field is a naive local-time string
    paired with a *separate* timeZone name — it doesn't accept an embedded
    UTC offset. This used to pass start_iso straight through with
    timeZone hardcoded to 'UTC' regardless of what offset it actually
    carried, silently creating the event several hours off from what the
    caller meant everywhere west of Greenwich. -04:00 14:00 must land as
    18:00 UTC, not literally '14:00' relabeled as UTC."""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({"subject": "Meeting", "id": "e2"})

    monkeypatch.setattr(cal.client, "post", fake_post)

    result = cal.CreateOutlookEventTool().run(summary="Meeting", start_iso="2026-08-12T14:00:00-04:00")

    assert captured["json"]["start"]["dateTime"] == "2026-08-12T18:00:00"
    assert captured["json"]["start"]["timeZone"] == "UTC"
    assert captured["json"]["end"]["dateTime"] == "2026-08-12T19:00:00"  # start + 1h, same conversion
    assert "Event created" in result


def test_create_event_uses_explicit_end_time(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({"subject": "Meeting", "id": "e2"})

    monkeypatch.setattr(cal.client, "post", fake_post)

    cal.CreateOutlookEventTool().run(
        summary="Meeting", start_iso="2026-08-12T14:00:00-04:00", end_iso="2026-08-12T16:00:00-04:00"
    )

    assert captured["json"]["end"]["dateTime"] == "2026-08-12T20:00:00"


def test_create_event_rejects_a_bare_local_time_with_no_utc_offset(monkeypatch):
    """A naive '2026-08-12T14:00:00' is ambiguous — which timezone is it in
    the caller's head? Silently assuming UTC is exactly the bug above;
    raising a clear, actionable error instead is the fix."""
    monkeypatch.setattr(cal.client, "post", lambda *a, **kw: _FakeResponse({}))

    with pytest.raises(ValueError, match="UTC offset"):
        cal.CreateOutlookEventTool().run(summary="Meeting", start_iso="2026-08-12T14:00:00")

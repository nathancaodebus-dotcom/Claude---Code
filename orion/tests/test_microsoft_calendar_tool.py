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
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({"subject": "Meeting", "id": "e2"})

    monkeypatch.setattr(cal.client, "post", fake_post)

    result = cal.CreateOutlookEventTool().run(summary="Meeting", start_iso="2026-08-12T14:00:00")

    assert captured["json"]["start"]["dateTime"] == "2026-08-12T14:00:00"
    assert captured["json"]["end"]["dateTime"] == "2026-08-12T15:00:00"
    assert "Event created" in result


def test_create_event_uses_explicit_end_time(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({"subject": "Meeting", "id": "e2"})

    monkeypatch.setattr(cal.client, "post", fake_post)

    cal.CreateOutlookEventTool().run(
        summary="Meeting", start_iso="2026-08-12T14:00:00", end_iso="2026-08-12T16:00:00"
    )

    assert captured["json"]["end"]["dateTime"] == "2026-08-12T16:00:00"

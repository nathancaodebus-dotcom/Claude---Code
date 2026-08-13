import datetime as dt

import pytest

from core.config import config
from tools import caldav_tools


@pytest.fixture(autouse=True)
def caldav_config():
    object.__setattr__(config, "caldav_url", "https://caldav.example.com")
    object.__setattr__(config, "caldav_username", "user")
    object.__setattr__(config, "caldav_password", "pass")
    yield
    object.__setattr__(config, "caldav_url", None)
    object.__setattr__(config, "caldav_username", None)
    object.__setattr__(config, "caldav_password", None)


class _FakeEvent:
    def __init__(self, summary, dtstart):
        self.icalendar_component = {"summary": summary, "dtstart": _FakeDt(dtstart)}


class _FakeDt:
    def __init__(self, value):
        self.dt = value


class _FakeCalendar:
    def __init__(self, name, events=None):
        self.name = name
        self._events = events or []

    def search(self, start, end, event, expand):
        return self._events

    def save_event(self, dtstart, dtend, summary):
        self.saved = {"dtstart": dtstart, "dtend": dtend, "summary": summary}
        return self


class _FakePrincipal:
    def __init__(self, calendars):
        self._calendars = calendars

    def calendars(self):
        return self._calendars


class _FakeDAVClient:
    instances = []

    def __init__(self, url, username, password):
        self.closed = False
        self.calendars = []
        _FakeDAVClient.instances.append(self)

    def principal(self):
        return _FakePrincipal(self.calendars)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


@pytest.fixture(autouse=True)
def fake_dav_client(monkeypatch):
    _FakeDAVClient.instances = []
    monkeypatch.setattr(caldav_tools.caldav, "DAVClient", _FakeDAVClient)
    return _FakeDAVClient


def test_missing_config_raises():
    object.__setattr__(config, "caldav_url", None)
    with pytest.raises(RuntimeError, match="not configured"):
        caldav_tools.ListCaldavEventsTool().run()


def test_list_events_closes_the_client_when_done(fake_dav_client):
    caldav_tools.ListCaldavEventsTool().run()

    assert len(fake_dav_client.instances) == 1
    assert fake_dav_client.instances[0].closed is True


def test_list_events_formats_results(fake_dav_client, monkeypatch):
    calendar = _FakeCalendar("Work", events=[_FakeEvent("Standup", dt.datetime(2026, 8, 12, 9, 0))])

    def init_with_calendar(self, url, username, password):
        self.closed = False
        self.calendars = [calendar]
        _FakeDAVClient.instances.append(self)

    monkeypatch.setattr(fake_dav_client, "__init__", init_with_calendar)

    result = caldav_tools.ListCaldavEventsTool().run()

    assert "Standup" in result
    assert "Work" in result


def test_list_events_no_upcoming(fake_dav_client):
    result = caldav_tools.ListCaldavEventsTool().run()
    assert result == "No upcoming CalDAV events."


def test_create_event_closes_the_client_when_done(fake_dav_client, monkeypatch):
    calendar = _FakeCalendar("Work")

    def init_with_calendar(self, url, username, password):
        self.closed = False
        self.calendars = [calendar]
        _FakeDAVClient.instances.append(self)

    monkeypatch.setattr(fake_dav_client, "__init__", init_with_calendar)

    result = caldav_tools.CreateCaldavEventTool().run(summary="Meeting", start_iso="2026-08-12T14:00:00-04:00")

    assert "Meeting" in result
    assert fake_dav_client.instances[0].closed is True


def test_create_event_no_calendars(fake_dav_client):
    result = caldav_tools.CreateCaldavEventTool().run(summary="Meeting", start_iso="2026-08-12T14:00:00-04:00")
    assert "No CalDAV calendars found" in result

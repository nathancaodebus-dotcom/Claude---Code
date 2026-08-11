import pytest

from tools import microsoft_contacts_tool as contacts


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
    monkeypatch.setattr(contacts, "get_access_token", lambda: "fake-token")


def test_search_no_matches(monkeypatch):
    monkeypatch.setattr(contacts.httpx, "get", lambda *a, **kw: _FakeResponse({"value": []}))
    result = contacts.SearchOutlookContactsTool().run(query="Nathan")
    assert "No contacts found" in result


def test_search_formats_results(monkeypatch):
    data = {
        "value": [
            {
                "displayName": "Nathan Cao",
                "emailAddresses": [{"address": "nathan@example.com"}],
                "businessPhones": ["0123456789"],
                "mobilePhone": "0798765432",
            }
        ]
    }
    monkeypatch.setattr(contacts.httpx, "get", lambda *a, **kw: _FakeResponse(data))

    result = contacts.SearchOutlookContactsTool().run(query="Nathan")

    assert "Nathan Cao" in result
    assert "nathan@example.com" in result
    assert "0123456789" in result
    assert "0798765432" in result


def test_search_escapes_single_quotes_in_filter(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse({"value": []})

    monkeypatch.setattr(contacts.httpx, "get", fake_get)

    contacts.SearchOutlookContactsTool().run(query="O'Brien")

    assert "O''Brien" in captured["params"]["$filter"]


def test_add_contact_minimal(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({})

    monkeypatch.setattr(contacts.httpx, "post", fake_post)

    result = contacts.AddOutlookContactTool().run(name="Nathan")

    assert result == "Added contact: Nathan"
    assert captured["json"] == {"givenName": "Nathan"}


def test_add_contact_with_email_and_phone(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({})

    monkeypatch.setattr(contacts.httpx, "post", fake_post)

    contacts.AddOutlookContactTool().run(name="Nathan", email="n@example.com", phone="0798765432")

    assert captured["json"]["emailAddresses"] == [{"address": "n@example.com", "name": "Nathan"}]
    assert captured["json"]["mobilePhone"] == "0798765432"

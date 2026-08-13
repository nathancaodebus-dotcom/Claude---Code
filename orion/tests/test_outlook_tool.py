import pytest

from tools import outlook_tool


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
    monkeypatch.setattr(outlook_tool, "get_access_token", lambda: "fake-token")


def test_search_returns_no_matches_message(monkeypatch):
    monkeypatch.setattr(outlook_tool.client, "get", lambda *a, **kw: _FakeResponse({"value": []}))
    result = outlook_tool.OutlookSearchTool().run()
    assert result == "No matching emails found."


def test_search_defaults_to_unread_filter(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse({"value": []})

    monkeypatch.setattr(outlook_tool.client, "get", fake_get)

    outlook_tool.OutlookSearchTool().run()

    assert captured["params"]["$filter"] == "isRead eq false"


def test_search_with_query_uses_search_param(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse({"value": []})

    monkeypatch.setattr(outlook_tool.client, "get", fake_get)

    outlook_tool.OutlookSearchTool().run(query="invoice")

    assert captured["params"]["$search"] == '"invoice"'
    assert "$filter" not in captured["params"]


def test_search_formats_results(monkeypatch):
    messages = {
        "value": [
            {
                "id": "abc123",
                "subject": "Hello",
                "from": {"emailAddress": {"address": "boss@example.com"}},
                "receivedDateTime": "2026-08-01T10:00:00Z",
                "bodyPreview": "hi there",
            }
        ]
    }
    monkeypatch.setattr(outlook_tool.client, "get", lambda *a, **kw: _FakeResponse(messages))

    result = outlook_tool.OutlookSearchTool().run()

    assert "abc123" in result
    assert "boss@example.com" in result
    assert "Hello" in result


def test_read_email_returns_body(monkeypatch):
    msg = {
        "subject": "Hi",
        "from": {"emailAddress": {"address": "a@b.com"}},
        "receivedDateTime": "2026-08-01T10:00:00Z",
        "body": {"content": "the body text"},
    }
    monkeypatch.setattr(outlook_tool.client, "get", lambda *a, **kw: _FakeResponse(msg))

    result = outlook_tool.OutlookReadTool().run(message_id="abc")

    assert "the body text" in result
    assert "a@b.com" in result


def test_create_draft_does_not_send(monkeypatch):
    monkeypatch.setattr(outlook_tool.client, "post", lambda *a, **kw: _FakeResponse({"id": "draft1"}))

    result = outlook_tool.OutlookCreateDraftTool().run(to="a@b.com", subject="Sub", body="Body")

    assert "Draft created" in result
    assert "Not sent" in result


def test_archive_moves_to_archive_folder(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse({})

    monkeypatch.setattr(outlook_tool.client, "post", fake_post)

    result = outlook_tool.OutlookArchiveTool().run(message_id="abc")

    assert "Archived email abc" in result
    assert captured["json"] == {"destinationId": "archive"}
    assert captured["url"].endswith("/me/messages/abc/move")


def test_mark_read_patches_is_read(monkeypatch):
    captured = {}

    def fake_patch(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({})

    monkeypatch.setattr(outlook_tool.client, "patch", fake_patch)

    result = outlook_tool.OutlookMarkReadTool().run(message_id="abc")

    assert "Marked email abc as read" in result
    assert captured["json"] == {"isRead": True}


def test_unread_count(monkeypatch):
    monkeypatch.setattr(outlook_tool.client, "get", lambda *a, **kw: _FakeResponse({"unreadItemCount": 7}))

    result = outlook_tool.OutlookUnreadCountTool().run()

    assert result == "7 unread email(s)."

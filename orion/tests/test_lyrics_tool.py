from tools.lyrics_tool import GetLyricsTool


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json_data = json_data or {}
        self.status_code = status_code

    def json(self):
        return self._json_data


def test_get_lyrics_returns_lyrics_on_success(monkeypatch):
    monkeypatch.setattr("tools.lyrics_tool.client.get", lambda *a, **kw: _FakeResponse({"lyrics": "La la la"}))
    result = GetLyricsTool().run(artist="Test Artist", title="Test Song")
    assert result == "La la la"


def test_get_lyrics_reports_not_found(monkeypatch):
    monkeypatch.setattr("tools.lyrics_tool.client.get", lambda *a, **kw: _FakeResponse(status_code=404))
    result = GetLyricsTool().run(artist="Nobody", title="Nothing")
    assert "No lyrics found" in result


def test_get_lyrics_url_encodes_a_slash_in_the_artist_name(monkeypatch):
    """Regression test: artist/title are interpolated as URL path
    segments — an unescaped '/' in the artist name (e.g. 'AC/DC') used to
    turn into an extra path segment instead of a literal character, so the
    API saw the wrong number of segments and 404d for a song that
    obviously has lyrics."""
    captured = {}

    def fake_get(url, timeout=None):
        captured["url"] = url
        return _FakeResponse({"lyrics": "Thunder"})

    monkeypatch.setattr("tools.lyrics_tool.client.get", fake_get)

    GetLyricsTool().run(artist="AC/DC", title="Thunderstruck")

    assert "AC%2FDC" in captured["url"]
    assert captured["url"].count("/v1/") == 1
    # Exactly two path segments after /v1/ — the encoded artist, then title.
    assert captured["url"].split("/v1/")[1].split("/") == ["AC%2FDC", "Thunderstruck"]

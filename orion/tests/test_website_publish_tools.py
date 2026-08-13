import pytest

from core.config import config
from core.store import Store
from tools.website_publish_tools import PublishWebsiteToGithubPagesTool
from tools.website_tools import CreateWebsiteTool


class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data or "")

    def json(self):
        return self._json_data


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = Store(db_path=str(tmp_path / "test.db"))
    CreateWebsiteTool(store).run(
        title="My Site", pages=[{"slug": "index", "title": "Home", "content_html": "<p>hi</p>"}]
    )
    return store


@pytest.fixture(autouse=True)
def github_pages_config():
    # config is a frozen dataclass — setattr must bypass __setattr__.
    object.__setattr__(config, "github_pages_owner", "nathan")
    object.__setattr__(config, "github_pages_token", "ghp_fake")
    yield
    object.__setattr__(config, "github_pages_owner", None)
    object.__setattr__(config, "github_pages_token", None)


def _install_fake_github(monkeypatch, *, repo_exists, contents_exist, pages_status=201):
    calls = {"get": [], "post": [], "put": []}

    def fake_get(url, **kwargs):
        calls["get"].append(url)
        if url.endswith("/repos/nathan/my-site"):
            return _FakeResponse(200 if repo_exists else 404)
        if "/contents/" in url:
            return _FakeResponse(200, {"sha": "abc123"}) if contents_exist else _FakeResponse(404)
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, **kwargs):
        calls["post"].append(url)
        if url.endswith("/user/repos"):
            return _FakeResponse(201)
        if url.endswith("/pages"):
            return _FakeResponse(pages_status)
        raise AssertionError(f"unexpected POST {url}")

    def fake_put(url, **kwargs):
        calls["put"].append(url)
        return _FakeResponse(201)

    monkeypatch.setattr("tools.website_publish_tools.client.get", fake_get)
    monkeypatch.setattr("tools.website_publish_tools.client.post", fake_post)
    monkeypatch.setattr("tools.website_publish_tools.client.put", fake_put)
    return calls


def test_publish_missing_site_gives_clear_error(store):
    result = PublishWebsiteToGithubPagesTool(store).run(site_name="does-not-exist")
    assert "No website named" in result


def test_publish_creates_repo_when_missing_and_returns_url(store, monkeypatch):
    calls = _install_fake_github(monkeypatch, repo_exists=False, contents_exist=False)

    result = PublishWebsiteToGithubPagesTool(store).run(site_name="my-site")

    assert result == "Published to https://nathan.github.io/my-site/ (may take a minute to go live)."
    assert any(url.endswith("/user/repos") for url in calls["post"])
    assert len(calls["put"]) >= 2  # index.html + style.css at minimum


def test_publish_reuses_existing_repo(store, monkeypatch):
    calls = _install_fake_github(monkeypatch, repo_exists=True, contents_exist=True)

    result = PublishWebsiteToGithubPagesTool(store).run(site_name="my-site")

    assert "Published to" in result
    assert not any(url.endswith("/user/repos") for url in calls["post"])


def test_publish_treats_pages_already_enabled_as_success(store, monkeypatch):
    _install_fake_github(monkeypatch, repo_exists=True, contents_exist=True, pages_status=409)

    result = PublishWebsiteToGithubPagesTool(store).run(site_name="my-site")

    assert "Published to" in result


def test_publish_reports_repo_creation_failure(store, monkeypatch):
    def fake_get(url, **kwargs):
        return _FakeResponse(404)

    def fake_post(url, **kwargs):
        if url.endswith("/user/repos"):
            return _FakeResponse(422, text="name already taken")
        raise AssertionError

    monkeypatch.setattr("tools.website_publish_tools.client.get", fake_get)
    monkeypatch.setattr("tools.website_publish_tools.client.post", fake_post)

    result = PublishWebsiteToGithubPagesTool(store).run(site_name="my-site")

    assert "Could not create repo" in result


def test_publish_reports_upload_failure(store, monkeypatch):
    def fake_get(url, **kwargs):
        if "/contents/" in url:
            return _FakeResponse(404)
        return _FakeResponse(200)

    def fake_put(url, **kwargs):
        return _FakeResponse(403, text="forbidden")

    monkeypatch.setattr("tools.website_publish_tools.client.get", fake_get)
    monkeypatch.setattr("tools.website_publish_tools.client.put", fake_put)

    result = PublishWebsiteToGithubPagesTool(store).run(site_name="my-site")

    assert "Failed to upload" in result


def test_publish_reports_how_many_files_already_uploaded_before_a_failure(store, monkeypatch):
    """Regression test: a mid-publish failure leaves whatever uploaded
    before it live on GitHub (no rollback/retry) — the message used to
    only name the file that failed, giving the caller no way to tell which
    files (if any) already went out, leaving the resulting repo's state
    ambiguous."""
    put_calls = []

    def fake_get(url, **kwargs):
        if url.endswith("/repos/nathan/my-site"):
            return _FakeResponse(200)
        return _FakeResponse(404)

    def fake_put(url, **kwargs):
        put_calls.append(url)
        if len(put_calls) == 2:
            return _FakeResponse(403, text="forbidden")
        return _FakeResponse(201)

    monkeypatch.setattr("tools.website_publish_tools.client.get", fake_get)
    monkeypatch.setattr("tools.website_publish_tools.client.put", fake_put)

    result = PublishWebsiteToGithubPagesTool(store).run(site_name="my-site")

    assert "Failed to upload" in result
    assert "1/" in result  # exactly one file succeeded before the second one failed
    assert len(put_calls) == 2  # stopped immediately rather than continuing past the failure


def test_publish_reports_pages_enable_failure(store, monkeypatch):
    _install_fake_github(monkeypatch, repo_exists=True, contents_exist=True, pages_status=500)

    result = PublishWebsiteToGithubPagesTool(store).run(site_name="my-site")

    assert "couldn't enable Pages" in result

import paramiko
import pytest

from core.config import config
from core.store import Store
from tools.website_publish_tools import PublishWebsiteToInfomaniakTool
from tools.website_tools import CreateWebsiteTool


class _FakeSFTPClient:
    def __init__(self):
        self.existing_dirs: set[str] = set()
        self.put_calls: list[tuple[str, str]] = []

    def stat(self, path):
        if path not in self.existing_dirs:
            raise FileNotFoundError(path)
        return object()

    def mkdir(self, path):
        self.existing_dirs.add(path)

    def put(self, local_path, remote_path):
        self.put_calls.append((local_path, remote_path))

    def close(self):
        pass


class _FakeTransport:
    def __init__(self, address):
        self.address = address
        self.connect_exception = None

    def connect(self, username, password):
        if self.connect_exception:
            raise self.connect_exception

    def close(self):
        pass


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = Store(db_path=str(tmp_path / "test.db"))
    CreateWebsiteTool(store).run(
        title="My Site", pages=[{"slug": "index", "title": "Home", "content_html": "<p>hi</p>"}]
    )
    return store


@pytest.fixture(autouse=True)
def infomaniak_config():
    object.__setattr__(config, "infomaniak_ftp_host", "ftp.example.com")
    object.__setattr__(config, "infomaniak_ftp_username", "user")
    object.__setattr__(config, "infomaniak_ftp_password", "pass")
    yield
    object.__setattr__(config, "infomaniak_ftp_host", None)
    object.__setattr__(config, "infomaniak_ftp_username", None)
    object.__setattr__(config, "infomaniak_ftp_password", None)


def _install_fake_sftp(monkeypatch) -> _FakeSFTPClient:
    fake_sftp = _FakeSFTPClient()
    monkeypatch.setattr("tools.website_publish_tools.paramiko.Transport", _FakeTransport)
    monkeypatch.setattr(
        "tools.website_publish_tools.paramiko.SFTPClient.from_transport", lambda transport: fake_sftp
    )
    return fake_sftp


def test_missing_site_gives_clear_error(store):
    result = PublishWebsiteToInfomaniakTool(store).run(site_name="does-not-exist")
    assert "No website named" in result


def test_publish_uploads_every_file(store, monkeypatch):
    fake_sftp = _install_fake_sftp(monkeypatch)

    result = PublishWebsiteToInfomaniakTool(store).run(site_name="my-site")

    assert "Uploaded" in result
    remote_paths = [remote for _, remote in fake_sftp.put_calls]
    assert "my-site/index.html" in remote_paths
    assert "my-site/style.css" in remote_paths
    assert not any("_site.json" in p for p in remote_paths)  # internal manifest, never published


def test_publish_creates_missing_remote_directories(store, monkeypatch):
    fake_sftp = _install_fake_sftp(monkeypatch)

    PublishWebsiteToInfomaniakTool(store).run(site_name="my-site")

    assert "my-site" in fake_sftp.existing_dirs


def test_publish_respects_custom_remote_dir(store, monkeypatch):
    fake_sftp = _install_fake_sftp(monkeypatch)

    PublishWebsiteToInfomaniakTool(store).run(site_name="my-site", remote_dir="public_html/mysite")

    remote_paths = [remote for _, remote in fake_sftp.put_calls]
    assert "public_html/mysite/index.html" in remote_paths


def test_publish_reports_authentication_failure(store, monkeypatch):
    def fake_transport(address):
        t = _FakeTransport(address)
        t.connect_exception = paramiko.AuthenticationException()
        return t

    monkeypatch.setattr("tools.website_publish_tools.paramiko.Transport", fake_transport)

    result = PublishWebsiteToInfomaniakTool(store).run(site_name="my-site")

    assert "login failed" in result


def test_publish_reports_connection_failure(store, monkeypatch):
    def fake_transport(address):
        t = _FakeTransport(address)
        t.connect_exception = OSError("network unreachable")
        return t

    monkeypatch.setattr("tools.website_publish_tools.paramiko.Transport", fake_transport)

    result = PublishWebsiteToInfomaniakTool(store).run(site_name="my-site")

    assert "Could not connect" in result


def test_reports_missing_paramiko(store, monkeypatch):
    monkeypatch.setattr("tools.website_publish_tools.paramiko", None)

    result = PublishWebsiteToInfomaniakTool(store).run(site_name="my-site")

    assert "paramiko is not installed" in result

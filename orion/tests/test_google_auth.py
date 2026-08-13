import stat
import threading
import time

import pytest

import tools.google_auth as google_auth
from core.config import config


@pytest.fixture(autouse=True)
def google_config(tmp_path):
    object.__setattr__(config, "google_token_path", str(tmp_path / "token.json"))
    object.__setattr__(config, "google_credentials_path", str(tmp_path / "credentials.json"))
    yield
    object.__setattr__(config, "google_token_path", "./token.json")
    object.__setattr__(config, "google_credentials_path", "./credentials.json")


class _FakeCreds:
    def __init__(self, valid=True):
        self.valid = valid
        self.expired = False
        self.refresh_token = None

    def to_json(self):
        return '{"fake": "creds"}'


class _FakeFlow:
    def __init__(self, *a, **kw):
        pass

    @classmethod
    def from_client_secrets_file(cls, path, scopes):
        return cls()

    def run_local_server(self, port=0):
        return _FakeCreds()


def _write_fake_credentials_file():
    from pathlib import Path

    Path(config.google_credentials_path).write_text("{}")


def test_token_file_is_written_with_restrictive_permissions(monkeypatch, tmp_path):
    """Regression test: this file holds a live OAuth refresh token — a
    plain write_text() used to inherit the process umask, commonly leaving
    it group/world-readable."""
    _write_fake_credentials_file()
    monkeypatch.setattr(google_auth, "InstalledAppFlow", _FakeFlow)

    google_auth.get_credentials()

    mode = stat.S_IMODE((tmp_path / "token.json").stat().st_mode)
    assert mode == 0o600


def test_concurrent_calls_do_not_race_to_open_two_browser_flows(monkeypatch):
    """Regression test: core/agent.py dispatches a turn's tool calls
    concurrently — without a lock, two threads hitting a missing token at
    once could both open an independent local OAuth callback server/
    browser tab at the same time."""
    _write_fake_credentials_file()
    concurrent_starts = {"count": 0, "max": 0}
    lock = threading.Lock()

    class _SlowFlow(_FakeFlow):
        def run_local_server(self, port=0):
            with lock:
                concurrent_starts["count"] += 1
                concurrent_starts["max"] = max(concurrent_starts["max"], concurrent_starts["count"])
            time.sleep(0.1)
            with lock:
                concurrent_starts["count"] -= 1
            return _FakeCreds()

    monkeypatch.setattr(google_auth, "InstalledAppFlow", _SlowFlow)
    # Once the first thread through writes a token file, later threads see
    # it exists and would otherwise hit the real (strict) credentials
    # parser on our fake JSON blob — fake that read too so every thread
    # actually exercises the "no valid cached token yet" path this test
    # means to race.
    monkeypatch.setattr(
        google_auth.Credentials, "from_authorized_user_file", classmethod(lambda cls, *a, **kw: _FakeCreds())
    )

    threads = [threading.Thread(target=google_auth.get_credentials) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert concurrent_starts["max"] == 1, "more than one browser auth flow was started at the same time"


def test_missing_credentials_file_raises_a_clear_error():
    with pytest.raises(RuntimeError, match="credentials file not found"):
        google_auth.get_credentials()

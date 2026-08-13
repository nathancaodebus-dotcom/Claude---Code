import stat
import threading
import time

import pytest

import tools.microsoft_auth as microsoft_auth
from core.config import config


@pytest.fixture(autouse=True)
def microsoft_config(tmp_path):
    object.__setattr__(config, "microsoft_client_id", "client-123")
    object.__setattr__(config, "microsoft_token_path", str(tmp_path / "token.json"))
    yield
    object.__setattr__(config, "microsoft_client_id", None)
    object.__setattr__(config, "microsoft_token_path", "./microsoft_token.json")


class _FakeCache:
    def __init__(self):
        self.has_state_changed = True
        self.deserialized_with = None

    def deserialize(self, data):
        self.deserialized_with = data

    def serialize(self):
        return "{}"


class _FakeApp:
    def __init__(self, client_id, authority=None, token_cache=None):
        self.client_id = client_id
        self.token_cache = token_cache
        self.accounts = []

    def get_accounts(self):
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        return None

    def initiate_device_flow(self, scopes):
        return {"user_code": "ABCD1234", "message": "To sign in, visit https://microsoft.com/devicelogin"}

    def acquire_token_by_device_flow(self, flow):
        return {"access_token": "fake-token"}


def test_missing_client_id_raises():
    object.__setattr__(config, "microsoft_client_id", None)
    with pytest.raises(RuntimeError, match="MICROSOFT_CLIENT_ID"):
        microsoft_auth.get_access_token()


def test_device_flow_returns_token_and_prints_instructions(monkeypatch, capsys):
    monkeypatch.setattr(microsoft_auth.msal, "SerializableTokenCache", _FakeCache)
    monkeypatch.setattr(microsoft_auth.msal, "PublicClientApplication", _FakeApp)

    token = microsoft_auth.get_access_token()

    assert token == "fake-token"
    assert "devicelogin" in capsys.readouterr().out


def test_uses_cached_silent_token_when_available(monkeypatch):
    class _SilentApp(_FakeApp):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.accounts = [{"username": "nathan"}]

        def acquire_token_silent(self, scopes, account):
            return {"access_token": "cached-token"}

    monkeypatch.setattr(microsoft_auth.msal, "SerializableTokenCache", _FakeCache)
    monkeypatch.setattr(microsoft_auth.msal, "PublicClientApplication", _SilentApp)

    assert microsoft_auth.get_access_token() == "cached-token"


def test_device_flow_start_failure_raises(monkeypatch):
    class _BrokenFlowApp(_FakeApp):
        def initiate_device_flow(self, scopes):
            return {"error": "invalid_scope"}

    monkeypatch.setattr(microsoft_auth.msal, "SerializableTokenCache", _FakeCache)
    monkeypatch.setattr(microsoft_auth.msal, "PublicClientApplication", _BrokenFlowApp)

    with pytest.raises(RuntimeError, match="Could not start"):
        microsoft_auth.get_access_token()


def test_failed_token_acquisition_raises_with_reason(monkeypatch):
    class _FailingApp(_FakeApp):
        def acquire_token_by_device_flow(self, flow):
            return {"error_description": "user declined"}

    monkeypatch.setattr(microsoft_auth.msal, "SerializableTokenCache", _FakeCache)
    monkeypatch.setattr(microsoft_auth.msal, "PublicClientApplication", _FailingApp)

    with pytest.raises(RuntimeError, match="user declined"):
        microsoft_auth.get_access_token()


def test_writes_token_cache_to_disk_when_state_changed(monkeypatch, tmp_path):
    monkeypatch.setattr(microsoft_auth.msal, "SerializableTokenCache", _FakeCache)
    monkeypatch.setattr(microsoft_auth.msal, "PublicClientApplication", _FakeApp)

    microsoft_auth.get_access_token()

    assert (tmp_path / "token.json").exists()


def test_token_file_is_written_with_restrictive_permissions(monkeypatch, tmp_path):
    """Regression test: this file holds a live OAuth token — a plain
    write_text() used to inherit the process umask, commonly leaving it
    group/world-readable."""
    monkeypatch.setattr(microsoft_auth.msal, "SerializableTokenCache", _FakeCache)
    monkeypatch.setattr(microsoft_auth.msal, "PublicClientApplication", _FakeApp)

    microsoft_auth.get_access_token()

    mode = stat.S_IMODE((tmp_path / "token.json").stat().st_mode)
    assert mode == 0o600


def test_concurrent_calls_do_not_race_to_start_two_device_flows(monkeypatch, tmp_path):
    """Regression test: core/agent.py dispatches a turn's tool calls
    concurrently — without a lock, two threads hitting a not-yet-cached
    token at once could both start an independent device code flow at the
    same time, printing two different codes and blocking two worker
    threads on human input simultaneously."""
    concurrent_starts = {"count": 0, "max": 0}
    lock = threading.Lock()

    class _SlowFlowApp(_FakeApp):
        def initiate_device_flow(self, scopes):
            with lock:
                concurrent_starts["count"] += 1
                concurrent_starts["max"] = max(concurrent_starts["max"], concurrent_starts["count"])
            time.sleep(0.1)
            with lock:
                concurrent_starts["count"] -= 1
            return super().initiate_device_flow(scopes)

    monkeypatch.setattr(microsoft_auth.msal, "SerializableTokenCache", _FakeCache)
    monkeypatch.setattr(microsoft_auth.msal, "PublicClientApplication", _SlowFlowApp)

    threads = [threading.Thread(target=microsoft_auth.get_access_token) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert concurrent_starts["max"] == 1, "more than one device flow was started at the same time"


def test_reads_existing_token_cache_from_disk(monkeypatch, tmp_path):
    (tmp_path / "token.json").write_text('{"foo": "bar"}')

    monkeypatch.setattr(microsoft_auth.msal, "SerializableTokenCache", _FakeCache)
    monkeypatch.setattr(microsoft_auth.msal, "PublicClientApplication", _FakeApp)

    calls = []
    original_init = _FakeCache.__init__

    def tracking_init(self):
        original_init(self)
        calls.append(self)

    monkeypatch.setattr(_FakeCache, "__init__", tracking_init)

    microsoft_auth.get_access_token()

    assert calls[0].deserialized_with == '{"foo": "bar"}'

import httpx
import pytest

from core.http import UnsafeUrlError, client, require_public_http_url


def test_client_is_a_persistent_pooled_httpx_client():
    assert isinstance(client, httpx.Client)


def test_client_has_a_default_timeout_and_connection_limits():
    assert client.timeout.connect == 10.0
    pool = client._transport._pool
    assert pool._max_keepalive_connections == 20
    assert pool._max_connections == 50


def test_every_tool_module_that_calls_httpx_shares_the_same_client_instance():
    """Every tool file was migrated off the module-level httpx.get/post/...
    convenience functions (a fresh connection per call, no reuse possible)
    onto this shared client. Importing it from a handful of representative
    tool modules and checking they're all the exact same object is what
    actually proves the pooling works across tools, not just within one."""
    import tools.crypto_tools as crypto_tools
    import tools.info_tools as info_tools
    import tools.shopify_tools as shopify_tools
    import tools.web_tools as web_tools

    assert web_tools.client is client
    assert info_tools.client is client
    assert crypto_tools.client is client
    assert shopify_tools.client is client


# --- require_public_http_url (SSRF guard) --------------------------------


def test_require_public_http_url_allows_a_normal_public_domain(monkeypatch):
    # DNS resolution mocked so this stays deterministic regardless of
    # network/DNS availability in whatever environment runs the tests.
    monkeypatch.setattr(
        "core.http.socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    require_public_http_url("https://example.com/page")  # must not raise


def test_require_public_http_url_rejects_a_non_http_scheme():
    with pytest.raises(UnsafeUrlError, match="Unsupported URL scheme"):
        require_public_http_url("file:///etc/passwd")


def test_require_public_http_url_rejects_a_url_with_no_hostname():
    with pytest.raises(UnsafeUrlError, match="no hostname"):
        require_public_http_url("http://")


def test_require_public_http_url_rejects_loopback():
    with pytest.raises(UnsafeUrlError, match="private/internal address"):
        require_public_http_url("http://127.0.0.1/admin")


def test_require_public_http_url_rejects_localhost():
    with pytest.raises(UnsafeUrlError, match="private/internal address"):
        require_public_http_url("http://localhost:8080/")


def test_require_public_http_url_rejects_cloud_metadata_endpoint():
    with pytest.raises(UnsafeUrlError, match="private/internal address"):
        require_public_http_url("http://169.254.169.254/latest/meta-data/")


def test_require_public_http_url_rejects_private_lan_addresses():
    for host in ("10.0.0.1", "192.168.1.1", "172.16.0.1"):
        with pytest.raises(UnsafeUrlError, match="private/internal address"):
            require_public_http_url(f"http://{host}/")


def test_require_public_http_url_rejects_an_unresolvable_hostname(monkeypatch):
    import socket

    def _raise(host, port):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr("core.http.socket.getaddrinfo", _raise)
    with pytest.raises(UnsafeUrlError, match="Couldn't resolve"):
        require_public_http_url("http://this-host-should-not-exist.invalid/")

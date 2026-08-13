import httpx

from core.http import client


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

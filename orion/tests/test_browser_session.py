"""core/browser_session.py's BrowserSession, tested against a real local
HTTP server and a real Chromium instance (not mocked) -- mirrors
tests/test_mcp_client.py's approach of exercising the actual third-party
integration rather than faking its internals. Skips (rather than failing)
if Playwright's browser isn't installed in this environment --
`playwright install chromium` provisions it; see requirements-browser.txt."""
from __future__ import annotations

import http.server
import threading

import pytest

pytest.importorskip("playwright")

from core.browser_session import BrowserError, BrowserSession, _domain_allowed
from core.config import config

_INDEX_HTML = """<!DOCTYPE html><html><head><title>Test Page</title></head><body>
<h1>Hello</h1>
<a href="/page2.html">Go to page 2</a>
<input type="text" aria-label="Search box">
<button onclick="document.getElementById('out').innerText='clicked!'">Click me</button>
<div id="out"></div>
</body></html>"""

_PAGE2_HTML = "<!DOCTYPE html><html><head><title>Page 2</title></head><body><h1>Page 2</h1></body></html>"


@pytest.fixture(scope="module")
def test_server(tmp_path_factory):
    site_dir = tmp_path_factory.mktemp("browser_test_site")
    (site_dir / "index.html").write_text(_INDEX_HTML)
    (site_dir / "page2.html").write_text(_PAGE2_HTML)

    def handler(*args, **kwargs):
        return http.server.SimpleHTTPRequestHandler(*args, directory=str(site_dir), **kwargs)

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture
def session(test_server):
    s = BrowserSession()
    try:
        s.navigate(f"{test_server}/index.html")
    except BrowserError as exc:
        s.close()
        pytest.skip(f"Playwright browser not launchable in this environment: {exc}")
    yield s
    s.close()


# --- _domain_allowed (pure function, no browser needed) ---------------------


def test_domain_allowed_matches_exact_domain():
    assert _domain_allowed("https://example.com/path", ["example.com"]) is True


def test_domain_allowed_matches_subdomain():
    assert _domain_allowed("https://shop.example.com/cart", ["example.com"]) is True


def test_domain_allowed_rejects_other_domains():
    assert _domain_allowed("https://evil.com/", ["example.com"]) is False


def test_domain_allowed_does_not_match_lookalike_domains():
    # "notexample.com" ends with "example.com" as a raw string but is a
    # different domain -- the subdomain check requires a literal '.' before
    # the allowed suffix so this must NOT match.
    assert _domain_allowed("https://notexample.com/", ["example.com"]) is False


# --- domain allowlist enforcement (no browser launch needed) ----------------


def test_navigate_blocks_disallowed_domain_without_launching_a_browser():
    object.__setattr__(config, "browser_allowed_domains", "trusted.example")
    try:
        s = BrowserSession()
        with pytest.raises(BrowserError, match="not on the configured browser domain allowlist"):
            s.navigate("https://not-trusted.example/")
        # The block happens before anything touches Playwright -- no
        # background thread (and so no browser) should ever have started.
        assert s._thread is None
    finally:
        object.__setattr__(config, "browser_allowed_domains", None)


def test_navigate_allows_domains_on_the_allowlist(test_server):
    host = test_server.split("://")[1].split(":")[0]
    object.__setattr__(config, "browser_allowed_domains", host)
    try:
        s = BrowserSession()
        try:
            state = s.navigate(f"{test_server}/index.html")
        except BrowserError as exc:
            pytest.skip(f"Playwright browser not launchable in this environment: {exc}")
        assert state.title == "Test Page"
        s.close()
    finally:
        object.__setattr__(config, "browser_allowed_domains", None)


# --- real browser session behavior -------------------------------------


def test_navigate_returns_title_url_and_elements(session, test_server):
    state = session.navigate(f"{test_server}/index.html")

    assert state.title == "Test Page"
    assert state.url == f"{test_server}/index.html"
    texts = {el.text for el in state.elements}
    assert "Go to page 2" in texts
    assert "Click me" in texts


def test_click_button_updates_page_text(session, test_server):
    state = session.navigate(f"{test_server}/index.html")
    click_ref = next(e.ref for e in state.elements if e.text == "Click me")

    session.click(click_ref)

    assert "clicked!" in session.get_text()


def test_click_link_navigates_to_a_new_page(session, test_server):
    state = session.navigate(f"{test_server}/index.html")
    link_ref = next(e.ref for e in state.elements if e.text == "Go to page 2")

    new_state = session.click(link_ref)

    assert new_state.url == f"{test_server}/page2.html"
    assert new_state.title == "Page 2"


def test_fill_sets_input_without_raising(session, test_server):
    state = session.navigate(f"{test_server}/index.html")
    input_ref = next(e.ref for e in state.elements if e.tag == "input")

    new_state = session.fill(input_ref, "hello world")

    assert new_state.title == "Test Page"


def test_get_text_returns_visible_page_text(session, test_server):
    session.navigate(f"{test_server}/index.html")

    text = session.get_text()

    assert "Hello" in text


def test_screenshot_returns_png_bytes(session, test_server):
    session.navigate(f"{test_server}/index.html")

    png_bytes = session.screenshot()

    assert png_bytes.startswith(b"\x89PNG")


def test_click_unknown_ref_raises_browser_error(session, test_server):
    session.navigate(f"{test_server}/index.html")

    with pytest.raises(BrowserError, match="No element with ref"):
        session.click(9999)


def test_fill_unknown_ref_raises_browser_error(session, test_server):
    session.navigate(f"{test_server}/index.html")

    with pytest.raises(BrowserError, match="No element with ref"):
        session.fill(9999, "text")


def test_close_before_any_use_does_not_raise():
    s = BrowserSession()
    s.close()  # never navigated anywhere -- should be a clean no-op


def test_close_is_idempotent(session):
    session.close()
    session.close()  # should not raise a second time

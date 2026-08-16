"""Playwright-backed browser automation session: navigate/click/fill/read
tools for sites with no API (tools/browser_tools.py), inspired by
OpenJarvis's browser.py/browser_axtree.py.

Playwright's sync API is not thread-safe across arbitrary callers — every
call has to happen on the same OS thread that started it. core/agent.py's
tool-use loop dispatches tool calls concurrently across a ThreadPoolExecutor
(any worker thread could call a browser tool), so BrowserSession owns one
dedicated background thread for the process's lifetime and forwards every
call to it through a queue, blocking the caller on a concurrent.futures.Future
for the result — the same call-forwarding shape core/mcp_client.py's
MCPManager uses for its own (different) thread-affinity constraint. The
browser itself launches lazily on first real use, not at import/registration
time — unlike MCPManager, which has to connect eagerly to know what tools
even exist, this module's tool set is fixed and hand-written, so there's no
reason to pay Chromium's ~1-2s launch cost on every process start.

Two safety choices are made once here, architecturally, rather than left to
the model's judgement per call:

- A fresh, non-persistent browser context every session: no access to the
  user's real browser profile, saved passwords, or autofill/payment data.
  Whatever Orion does in this browser, it can only do starting from a
  logged-out, empty state — eliminates the worst failure mode (silently
  riding an existing logged-in session to complete a purchase) by
  construction, not by hoping the model behaves.
- An optional domain allowlist (BROWSER_ALLOWED_DOMAINS), enforced in
  navigate() before anything reaches the browser — the same "pre-approved,
  not arbitrary" shape tools/deploy_tool.py already uses for shell
  commands. Off by default (browsing anywhere), matching tools/web_tools.py's
  existing unrestricted web_search/fetch_webpage; set it to scope Orion to
  specific trusted sites for click/fill workflows.
"""
from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable, TypeVar
from urllib.parse import urlparse

from core.config import config

_LAUNCH_TIMEOUT_S = 30.0
_CALL_TIMEOUT_S = 30.0
_ACTION_TIMEOUT_MS = 10_000
_MAX_ELEMENTS = 60
_MAX_TEXT_CHARS = 4000

T = TypeVar("T")

# Tags/roles/attributes elements typically the interesting to a browsing
# agent (link, button, form field). Filtered to visible ones only — a page
# full of hidden nav/modal markup would otherwise flood the ref list with
# elements nothing can actually click. Every match gets tagged with its ref
# as a data attribute so the click()/fill() selectors below can address it
# directly and stably, instead of re-deriving a CSS selector that might not
# even be unique.
_EXTRACT_ELEMENTS_JS = """
() => {
  const els = Array.from(document.querySelectorAll(
    'a, button, input, textarea, select, [role="button"], [role="link"], [onclick]'
  ));
  return els.filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !el.disabled;
  }).map((el, i) => {
    el.setAttribute('data-orion-ref', String(i));
    const label = el.getAttribute('aria-label') || el.getAttribute('placeholder')
      || el.innerText || el.value || el.name || '';
    return {
      ref: i,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      text: label.trim().replace(/\\s+/g, ' ').slice(0, 80),
    };
  });
}
"""


class BrowserError(RuntimeError):
    """Raised for browser-automation failures a Tool.run() should surface
    to the model as plain text (blocked domain, unknown ref, page failed
    to load, ...) rather than as an uncaught exception."""


@dataclass(frozen=True)
class ElementInfo:
    ref: int
    tag: str
    type: str
    text: str


@dataclass(frozen=True)
class PageState:
    url: str
    title: str
    elements: list[ElementInfo]
    truncated: bool


def _allowed_domains() -> list[str]:
    raw = config.browser_allowed_domains
    if not raw:
        return []
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _domain_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


class BrowserSession:
    """One persistent, isolated Chromium session for the process's
    lifetime. tools/browser_tools.py creates a single module-level
    instance, matching every other singleton-session integration in this
    codebase (core/http.py's shared client, core/mcp_client.py's
    MCPManager)."""

    def __init__(self) -> None:
        self._queue: queue.Queue | None = None
        self._thread: threading.Thread | None = None
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def navigate(self, url: str) -> PageState:
        allowed = _allowed_domains()
        if allowed and not _domain_allowed(url, allowed):
            raise BrowserError(
                f"'{url}' is not on the configured browser domain allowlist ({', '.join(allowed)})."
            )
        return self._run(lambda: self._navigate(url))

    def click(self, ref: int) -> PageState:
        return self._run(lambda: self._click(ref))

    def fill(self, ref: int, text: str) -> PageState:
        return self._run(lambda: self._fill(ref, text))

    def get_text(self, max_chars: int = _MAX_TEXT_CHARS) -> str:
        return self._run(lambda: self._get_text(max_chars))

    def screenshot(self) -> bytes:
        return self._run(self._screenshot)

    def close(self) -> None:
        if self._queue is None:
            return
        try:
            self._run(self._close_browser)
        except BrowserError:
            pass
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._queue = None
        self._thread = None

    # --- thread plumbing ---------------------------------------------------

    def _ensure_thread(self) -> None:
        if self._thread is not None:
            return
        self._queue = queue.Queue()
        ready = threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(ready,), name="orion-browser", daemon=True)
        self._thread.start()
        ready.wait(timeout=5)

    def _loop(self, ready: threading.Event) -> None:
        ready.set()
        while True:
            item = self._queue.get()
            if item is None:
                return
            fn, future = item
            try:
                future.set_result(fn())
            except BaseException as exc:  # noqa: BLE001 - forwarded to the caller's thread via the future
                future.set_exception(exc)

    def _run(self, fn: Callable[[], T]) -> T:
        self._ensure_thread()
        future: Future = Future()
        self._queue.put((fn, future))
        return future.result(timeout=_CALL_TIMEOUT_S)

    # --- browser-thread-only methods (never call these outside _run) -------

    def _ensure_page(self):
        if self._page is not None:
            return self._page
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        try:
            self._playwright = sync_playwright().start()
            # Playwright's own bundled Chromium download (~300MB) is the
            # default, but a Raspberry Pi or other low-resource device
            # this project already targets (see README §7/§8) is more
            # likely to already have a much smaller apt-installed
            # chromium-browser -- BROWSER_CHROMIUM_EXECUTABLE_PATH points
            # at that instead of fetching Playwright's own copy. None (the
            # default) uses Playwright's normal resolution.
            self._browser = self._playwright.chromium.launch(
                headless=True, executable_path=config.browser_chromium_executable_path or None
            )
            # A fresh, non-persistent context every session -- no cookies,
            # saved passwords, or autofill data carried over from
            # anywhere, see the module docstring.
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
        except PlaywrightError as exc:
            raise BrowserError(
                f"Couldn't launch the browser: {exc}. If Playwright's browser isn't installed, run "
                "`playwright install chromium`, or set BROWSER_CHROMIUM_EXECUTABLE_PATH to an "
                "existing Chromium binary."
            ) from exc
        return self._page

    def _enforce_domain_allowlist(self, page) -> None:
        """navigate()'s own pre-check (before this session ever requests
        the URL) only validates the *requested* string -- it can't catch a
        server-side redirect to a different domain, and click() has no
        pre-check at all, since a click's destination isn't known until
        after it navigates. Calling this from _extract_state(), which
        every action method (_navigate/_click/_fill) routes through after
        the page has settled, catches the *actual resulting* page.url
        regardless of how it got there -- found during a full-codebase
        audit: a link on an otherwise-allowlisted page could navigate the
        shared, persistent session to any non-allowlisted domain with
        click() alone, silently defeating BROWSER_ALLOWED_DOMAINS."""
        allowed = _allowed_domains()
        if not allowed or _domain_allowed(page.url, allowed):
            return
        blocked_url = page.url
        page.goto("about:blank")
        raise BrowserError(
            f"Blocked: ended up on '{blocked_url}', which is not on the configured browser domain "
            f"allowlist ({', '.join(allowed)}). Navigated to a blank page."
        )

    def _extract_state(self, page) -> PageState:
        self._enforce_domain_allowlist(page)
        raw_elements = page.evaluate(_EXTRACT_ELEMENTS_JS)
        truncated = len(raw_elements) > _MAX_ELEMENTS
        elements = [
            ElementInfo(ref=e["ref"], tag=e["tag"], type=e["type"], text=e["text"])
            for e in raw_elements[:_MAX_ELEMENTS]
        ]
        return PageState(url=page.url, title=page.title(), elements=elements, truncated=truncated)

    def _ref_selector(self, page, ref: int) -> str:
        selector = f'[data-orion-ref="{ref}"]'
        if page.locator(selector).count() == 0:
            raise BrowserError(
                f"No element with ref {ref} on the current page — the page may have changed since "
                "that ref was listed; call browser_navigate or browser_click again to refresh it."
            )
        return selector

    def _navigate(self, url: str) -> PageState:
        from playwright.sync_api import Error as PlaywrightError

        page = self._ensure_page()
        try:
            page.goto(url, timeout=_LAUNCH_TIMEOUT_S * 1000, wait_until="load")
        except PlaywrightError as exc:
            raise BrowserError(f"Couldn't load '{url}': {exc}") from exc
        return self._extract_state(page)

    def _click(self, ref: int) -> PageState:
        from playwright.sync_api import Error as PlaywrightError

        page = self._ensure_page()
        selector = self._ref_selector(page, ref)
        try:
            page.click(selector, timeout=_ACTION_TIMEOUT_MS)
            page.wait_for_load_state("load", timeout=_ACTION_TIMEOUT_MS)
        except PlaywrightError as exc:
            raise BrowserError(f"Couldn't click ref {ref}: {exc}") from exc
        return self._extract_state(page)

    def _fill(self, ref: int, text: str) -> PageState:
        from playwright.sync_api import Error as PlaywrightError

        page = self._ensure_page()
        selector = self._ref_selector(page, ref)
        try:
            page.fill(selector, text, timeout=_ACTION_TIMEOUT_MS)
        except PlaywrightError as exc:
            raise BrowserError(f"Couldn't fill ref {ref}: {exc}") from exc
        return self._extract_state(page)

    def _get_text(self, max_chars: int) -> str:
        page = self._ensure_page()
        text = page.inner_text("body")
        return " ".join(text.split())[:max_chars]

    def _screenshot(self) -> bytes:
        page = self._ensure_page()
        return page.screenshot(full_page=False)

    def _close_browser(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None

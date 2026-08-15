"""Playwright-backed browser automation: navigate, click, fill, and read
pages that have no API of their own — inspired by OpenJarvis's
browser.py/browser_axtree.py. See core/browser_session.py for the
session/threading model and the two safety choices (an isolated,
non-persistent browser context and an optional domain allowlist) baked in
architecturally rather than left to the model's judgement per call.

Elements are addressed by a small integer "ref" rather than a CSS selector
or free-text description — browser_navigate/browser_click/browser_fill
each return the current page's interactive elements (ref, tag, type,
visible label) so the model can pick a ref directly from what it was just
shown, instead of guessing selectors blind. A ref is only valid for the
page state it came from; a stale one (after a navigation changed the page)
is rejected with a message pointing at the current elements list rather
than silently clicking the wrong thing.
"""
from __future__ import annotations

import time

from core.attachments import push as push_attachment
from core.browser_session import BrowserError, BrowserSession, PageState
from tools.base import Tool
from tools.document_utils import OUTPUT_DIR


def _format_state(state: PageState) -> str:
    lines = [f"Title: {state.title}", f"URL: {state.url}", "Interactive elements:"]
    if not state.elements:
        lines.append("  (none found)")
    for el in state.elements:
        label = f' "{el.text}"' if el.text else ""
        kind = el.tag + (f"[{el.type}]" if el.type else "")
        lines.append(f"  ref={el.ref} {kind}{label}")
    if state.truncated:
        lines.append("  (more elements exist on this page but were truncated)")
    return "\n".join(lines)


class BrowserNavigateTool(Tool):
    name = "browser_navigate"
    description = (
        "Open a URL in a persistent, isolated browser session (no saved logins, passwords, or "
        "autofill/payment data carried over from anywhere) and return the page's title, URL, and a "
        "numbered list of interactive elements (links, buttons, inputs) to click or fill next with "
        "browser_click/browser_fill. Use this for sites with no API of their own -- prefer a proper "
        "API-backed tool (web_search, fetch_webpage, etc.) whenever one exists instead. If "
        "BROWSER_ALLOWED_DOMAINS is configured, only URLs on that allowlist can be opened."
    )
    input_schema = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}

    def __init__(self, session: BrowserSession) -> None:
        self._session = session

    def run(self, url: str) -> str:
        try:
            state = self._session.navigate(url)
        except BrowserError as exc:
            return str(exc)
        return _format_state(state)


class BrowserClickTool(Tool):
    name = "browser_click"
    description = (
        "Click the element with the given ref, from the list returned by the last "
        "browser_navigate/browser_click/browser_fill call. Returns the resulting page's title, URL, "
        "and updated element list. Never click something that submits a purchase, payment, "
        "deletion, or message without the user's explicit go-ahead in this conversation first -- "
        "this tool has no way to tell those apart from an ordinary click on its own."
    )
    input_schema = {"type": "object", "properties": {"ref": {"type": "integer"}}, "required": ["ref"]}

    def __init__(self, session: BrowserSession) -> None:
        self._session = session

    def run(self, ref: int) -> str:
        try:
            state = self._session.click(ref)
        except BrowserError as exc:
            return str(exc)
        return _format_state(state)


class BrowserFillTool(Tool):
    name = "browser_fill"
    description = (
        "Type text into the input/textarea with the given ref, from the list returned by the last "
        "browser_navigate/browser_click/browser_fill call. Does not submit the form on its own -- "
        "follow up with browser_click on the submit button when the user wants that."
    )
    input_schema = {
        "type": "object",
        "properties": {"ref": {"type": "integer"}, "text": {"type": "string"}},
        "required": ["ref", "text"],
    }

    def __init__(self, session: BrowserSession) -> None:
        self._session = session

    def run(self, ref: int, text: str) -> str:
        try:
            state = self._session.fill(ref, text)
        except BrowserError as exc:
            return str(exc)
        return _format_state(state)


class BrowserGetTextTool(Tool):
    name = "browser_get_text"
    description = (
        "Get the current page's visible text content -- for reading an article, search results, or "
        "any content that isn't a list of things to click. Truncated to a few thousand characters."
    )
    input_schema = {
        "type": "object",
        "properties": {"max_chars": {"type": "integer", "description": "Default 4000."}},
    }

    def __init__(self, session: BrowserSession) -> None:
        self._session = session

    def run(self, max_chars: int = 4000) -> str:
        try:
            text = self._session.get_text(max_chars)
        except BrowserError as exc:
            return str(exc)
        return text or "(page has no visible text)"


class BrowserScreenshotTool(Tool):
    name = "browser_screenshot"
    description = (
        "Save a screenshot of the current page as an image file, sent back to the user -- for "
        "showing what a page actually looks like rather than just its text or element list."
    )
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, session: BrowserSession) -> None:
        self._session = session

    def run(self) -> str:
        try:
            png_bytes = self._session.screenshot()
        except BrowserError as exc:
            return str(exc)

        output_dir = OUTPUT_DIR / "browser"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"screenshot-{int(time.time())}.png"
        path.write_bytes(png_bytes)
        push_attachment(str(path))
        return f"Screenshot saved to {path}."

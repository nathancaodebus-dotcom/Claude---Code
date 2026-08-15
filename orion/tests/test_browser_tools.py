"""tools/browser_tools.py wraps core/browser_session.py's BrowserSession as
Tool subclasses. Uses a fake session (no real browser) so this stays fast
and independent of Playwright being installed -- see
tests/test_browser_session.py for the real-browser integration coverage
these sit on top of."""
from __future__ import annotations

from core.browser_session import BrowserError, ElementInfo, PageState
from tools.browser_tools import (
    BrowserClickTool,
    BrowserFillTool,
    BrowserGetTextTool,
    BrowserNavigateTool,
    BrowserScreenshotTool,
)


class _FakeSession:
    def __init__(self):
        self.calls: list[tuple] = []
        self.next_state = PageState(
            url="https://example.com/",
            title="Example",
            elements=[ElementInfo(ref=0, tag="a", type="", text="A link")],
            truncated=False,
        )
        self.next_text = "some page text"
        self.next_screenshot = b"\x89PNGfakebytes"
        self.error: BrowserError | None = None

    def navigate(self, url: str) -> PageState:
        self.calls.append(("navigate", url))
        if self.error:
            raise self.error
        return self.next_state

    def click(self, ref: int) -> PageState:
        self.calls.append(("click", ref))
        if self.error:
            raise self.error
        return self.next_state

    def fill(self, ref: int, text: str) -> PageState:
        self.calls.append(("fill", ref, text))
        if self.error:
            raise self.error
        return self.next_state

    def get_text(self, max_chars: int = 4000) -> str:
        self.calls.append(("get_text", max_chars))
        if self.error:
            raise self.error
        return self.next_text

    def screenshot(self) -> bytes:
        self.calls.append(("screenshot",))
        if self.error:
            raise self.error
        return self.next_screenshot


# --- BrowserNavigateTool -----------------------------------------------


def test_navigate_formats_title_url_and_elements():
    session = _FakeSession()
    tool = BrowserNavigateTool(session)

    result = tool.run(url="https://example.com/")

    assert session.calls == [("navigate", "https://example.com/")]
    assert "Example" in result
    assert "https://example.com/" in result
    assert 'ref=0 a "A link"' in result


def test_navigate_returns_the_browser_error_message_instead_of_raising():
    session = _FakeSession()
    session.error = BrowserError("blocked domain")
    tool = BrowserNavigateTool(session)

    result = tool.run(url="https://blocked.example/")

    assert result == "blocked domain"


def test_navigate_reports_when_no_elements_are_found():
    session = _FakeSession()
    session.next_state = PageState(url="https://example.com/", title="Empty", elements=[], truncated=False)
    tool = BrowserNavigateTool(session)

    result = tool.run(url="https://example.com/")

    assert "(none found)" in result


def test_navigate_notes_truncation():
    session = _FakeSession()
    session.next_state = PageState(url="https://example.com/", title="Big", elements=[], truncated=True)
    tool = BrowserNavigateTool(session)

    result = tool.run(url="https://example.com/")

    assert "truncated" in result


# --- BrowserClickTool -----------------------------------------------------


def test_click_dispatches_to_the_session_with_the_given_ref():
    session = _FakeSession()
    tool = BrowserClickTool(session)

    result = tool.run(ref=0)

    assert session.calls == [("click", 0)]
    assert "Example" in result


def test_click_returns_the_browser_error_message_instead_of_raising():
    session = _FakeSession()
    session.error = BrowserError("No element with ref 9999 on the current page")
    tool = BrowserClickTool(session)

    result = tool.run(ref=9999)

    assert "No element with ref 9999" in result


# --- BrowserFillTool -------------------------------------------------------


def test_fill_dispatches_ref_and_text_to_the_session():
    session = _FakeSession()
    tool = BrowserFillTool(session)

    result = tool.run(ref=1, text="hello")

    assert session.calls == [("fill", 1, "hello")]
    assert "Example" in result


# --- BrowserGetTextTool -----------------------------------------------------


def test_get_text_returns_the_session_text():
    session = _FakeSession()
    tool = BrowserGetTextTool(session)

    result = tool.run(max_chars=100)

    assert session.calls == [("get_text", 100)]
    assert result == "some page text"


def test_get_text_reports_an_empty_page():
    session = _FakeSession()
    session.next_text = ""
    tool = BrowserGetTextTool(session)

    result = tool.run()

    assert "no visible text" in result


# --- BrowserScreenshotTool ---------------------------------------------


def test_screenshot_saves_a_file_and_pushes_an_attachment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = _FakeSession()
    tool = BrowserScreenshotTool(session)

    result = tool.run()

    assert session.calls == [("screenshot",)]
    assert "Screenshot saved to" in result
    saved_path = result.split("Screenshot saved to ", 1)[1].rstrip(".")
    from pathlib import Path

    assert Path(saved_path).read_bytes() == b"\x89PNGfakebytes"


def test_screenshot_returns_the_browser_error_message_instead_of_raising():
    session = _FakeSession()
    session.error = BrowserError("Couldn't launch the browser")
    tool = BrowserScreenshotTool(session)

    result = tool.run()

    assert result == "Couldn't launch the browser"

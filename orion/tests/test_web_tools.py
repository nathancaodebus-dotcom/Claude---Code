from tools.web_tools import WebSearchTool


class _FakeResponse:
    def __init__(self, text):
        self.text = text


_DDG_RESULT_HTML = """
<div class="result results_links results_links_deep web-result">
  <div class="result__body">
    <h2 class="result__title">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FPython&amp;rut=abc">
        Python (programming language)
      </a>
    </h2>
    <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FPython">
      Python is a high-level programming language.
    </a>
    <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FPython&amp;rut=abc">
      en.wikipedia.org/wiki/Python
    </a>
  </div>
</div>
"""


def test_web_search_decodes_the_real_url_from_the_ddg_redirect_wrapper(monkeypatch):
    """Regression test: .result__url's text is DuckDuckGo's scheme-less
    display string (e.g. 'en.wikipedia.org/wiki/Python'), not a usable
    URL — passing that straight to fetch_webpage used to raise an invalid-
    URL error since it has no scheme. The real destination is encoded in
    the element's href as a 'uddg' query parameter on DDG's redirect
    wrapper; decoding it gives back a directly fetchable URL."""
    monkeypatch.setattr(
        "tools.web_tools.client.get", lambda *a, **kw: _FakeResponse(_DDG_RESULT_HTML)
    )

    result = WebSearchTool().run(query="python programming")

    assert "https://en.wikipedia.org/wiki/Python" in result
    assert "Python (programming language)" in result


def test_web_search_falls_back_to_display_text_when_href_has_no_uddg_param(monkeypatch):
    html = """
    <div class="result">
      <div class="result__title"><a>Some Title</a></div>
      <div class="result__snippet">A snippet.</div>
      <a class="result__url" href="//example.com/no-redirect-wrapper">example.com/page</a>
    </div>
    """
    monkeypatch.setattr("tools.web_tools.client.get", lambda *a, **kw: _FakeResponse(html))

    result = WebSearchTool().run(query="anything")

    assert "example.com/page" in result


def test_web_search_reports_no_results(monkeypatch):
    monkeypatch.setattr("tools.web_tools.client.get", lambda *a, **kw: _FakeResponse("<html></html>"))
    result = WebSearchTool().run(query="nothing")
    assert result == "No results found."

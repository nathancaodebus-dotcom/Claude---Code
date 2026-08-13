import httpx
import pytest

from core.offline_agent import OFFLINE_REPLY_PREFIX, OfflineAgent, is_ollama_reachable
from tools.base import Tool, ToolRegistry


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes back the given text."
    input_schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    requires_network = False

    def run(self, text: str) -> str:
        return f"echoed: {text}"


class _NetworkTool(Tool):
    name = "get_weather"
    description = "Needs the internet."
    input_schema = {"type": "object", "properties": {}}
    # requires_network left at the Tool default (True)

    def run(self) -> str:
        return "sunny"


def _registry():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    reg.register(_NetworkTool())
    return reg


def test_is_ollama_reachable_true_on_200(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse({}, status_code=200))
    assert is_ollama_reachable("http://localhost:11434") is True


def test_is_ollama_reachable_false_on_non_200(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse({}, status_code=500))
    assert is_ollama_reachable("http://localhost:11434") is False


def test_is_ollama_reachable_false_on_connection_error(monkeypatch):
    def raise_connect_error(*a, **kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", raise_connect_error)
    assert is_ollama_reachable("http://localhost:11434") is False


def test_offline_agent_only_exposes_network_free_tools(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["tools"] = json["tools"]
        return _FakeResponse({"message": {"role": "assistant", "content": "hi"}})

    monkeypatch.setattr(httpx, "post", fake_post)

    agent = OfflineAgent(_registry(), "http://localhost:11434", "llama3.1:8b")
    agent.respond("hello")

    tool_names = [t["function"]["name"] for t in captured["tools"]]
    assert tool_names == ["echo"]  # only the offline-safe tool, not get_weather


def test_offline_agent_reply_is_prefixed(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda *a, **kw: _FakeResponse({"message": {"role": "assistant", "content": "Bonjour !"}})
    )
    agent = OfflineAgent(_registry(), "http://localhost:11434", "llama3.1:8b")

    result = agent.respond("salut")

    assert result == OFFLINE_REPLY_PREFIX + "Bonjour !"


def test_offline_agent_dispatches_tool_calls(monkeypatch):
    responses = [
        _FakeResponse(
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "echo", "arguments": {"text": "test"}}}],
                }
            }
        ),
        _FakeResponse({"message": {"role": "assistant", "content": "Done: echoed: test"}}),
    ]

    def fake_post(url, json=None, timeout=None):
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", fake_post)
    agent = OfflineAgent(_registry(), "http://localhost:11434", "llama3.1:8b")

    result = agent.respond("echo test please")

    assert result == OFFLINE_REPLY_PREFIX + "Done: echoed: test"


def test_offline_agent_sends_model_and_host(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["model"] = json["model"]
        return _FakeResponse({"message": {"role": "assistant", "content": "ok"}})

    monkeypatch.setattr(httpx, "post", fake_post)
    agent = OfflineAgent(_registry(), "http://my-host:11434/", "qwen2.5:14b")

    agent.respond("hi")

    assert captured["url"] == "http://my-host:11434/api/chat"
    assert captured["model"] == "qwen2.5:14b"

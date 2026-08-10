from core.memory import Memory
from tools.base import Tool, ToolRegistry
from tools.memory_tool import RecallFactsTool, RememberFactTool


class EchoTool(Tool):
    name = "echo"
    description = "Echoes its input."
    input_schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    def run(self, text: str) -> str:
        return text


class FailingTool(Tool):
    name = "boom"
    description = "Always raises."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        raise ValueError("kaboom")


def test_dispatch_calls_registered_tool():
    registry = ToolRegistry()
    registry.register(EchoTool())

    assert registry.dispatch("echo", {"text": "hi"}) == "hi"


def test_dispatch_unknown_tool_returns_error_string():
    registry = ToolRegistry()
    result = registry.dispatch("nope", {})
    assert "unknown tool" in result


def test_dispatch_catches_exceptions():
    registry = ToolRegistry()
    registry.register(FailingTool())

    result = registry.dispatch("boom", {})
    assert "kaboom" in result


def test_anthropic_schemas_shape():
    registry = ToolRegistry()
    registry.register(EchoTool())

    schemas = registry.anthropic_schemas()
    assert schemas == [
        {
            "name": "echo",
            "description": "Echoes its input.",
            "input_schema": EchoTool.input_schema,
        }
    ]


def test_remember_and_recall_fact_tools(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    remember = RememberFactTool(memory)
    recall = RecallFactsTool(memory)

    remember.run(key="dog_name", value="Rex")

    assert "Rex" in recall.run()

from core.memory import Memory
from tools.base import Tool, ToolRegistry
from tools.correction_tool import ListCorrectionsTool, LogCorrectionTool
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


def test_log_and_list_corrections_tools(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    log = LogCorrectionTool(memory)
    listing = ListCorrectionsTool(memory)

    result = log.run(category="tone", mistake="was too formal", correction="be casual")

    assert "tone" in result
    listed = listing.run()
    assert "was too formal" in listed
    assert "be casual" in listed


def test_log_correction_indexes_into_vector_memory_when_available(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))

    class _FakeVectorMemory:
        def __init__(self):
            self.indexed = []

        def index(self, text, source):
            self.indexed.append((text, source))

    vector_memory = _FakeVectorMemory()
    log = LogCorrectionTool(memory, vector_memory)

    log.run(category="tool_usage", mistake="used the wrong calendar", correction="use the work calendar")

    assert len(vector_memory.indexed) == 1
    text, source = vector_memory.indexed[0]
    assert "used the wrong calendar" in text
    assert source == "correction"


def test_list_corrections_reports_none_when_empty(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    listing = ListCorrectionsTool(memory)

    assert listing.run() == "No corrections logged yet."

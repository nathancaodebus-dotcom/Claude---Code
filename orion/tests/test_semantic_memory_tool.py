from core.vector_memory import MemoryMatch
from tools.semantic_memory_tool import IndexMemoryTool, SearchMemoryTool


class _FakeVectorMemory:
    def __init__(self, matches=None):
        self._matches = matches or []
        self.indexed = []
        self.searched_with = None

    def index(self, text, source):
        self.indexed.append((text, source))

    def search(self, query, top_k):
        self.searched_with = (query, top_k)
        return self._matches[:top_k]


def test_index_memory_delegates_to_vector_memory():
    memory = _FakeVectorMemory()
    result = IndexMemoryTool(memory).run(text="hello", source="chat")
    assert memory.indexed == [("hello", "chat")]
    assert "Indexed" in result


def test_search_memory_formats_matches():
    memory = _FakeVectorMemory([MemoryMatch(text="the thing", source="chat", score=0.9)])
    result = SearchMemoryTool(memory).run(query="thing")
    assert "the thing" in result
    assert "0.90" in result


def test_search_memory_reports_no_matches():
    memory = _FakeVectorMemory([])
    result = SearchMemoryTool(memory).run(query="nothing relevant")
    assert result == "No related memories found."


def test_search_memory_rejects_zero_max_results(monkeypatch):
    """Regression test: max_results=0 used to silently return zero
    matches, indistinguishable from '0 memories actually relate to your
    query' — misleading, since it really means 'you asked for zero'."""
    memory = _FakeVectorMemory([MemoryMatch(text="x", source="chat", score=0.5)])
    result = SearchMemoryTool(memory).run(query="x", max_results=0)
    assert "at least 1" in result
    assert memory.searched_with is None  # never even called search()


def test_search_memory_rejects_negative_max_results():
    """Regression test: a negative max_results used to reach
    core/vector_memory.py's np.argpartition with an out-of-bounds kth,
    raising a raw numpy internals error instead of a clean message."""
    memory = _FakeVectorMemory([MemoryMatch(text="x", source="chat", score=0.5)])
    result = SearchMemoryTool(memory).run(query="x", max_results=-1)
    assert "at least 1" in result

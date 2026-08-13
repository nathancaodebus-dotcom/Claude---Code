import pytest

from tools.obsidian_tools import AppendObsidianNoteTool, CreateObsidianNoteTool, ListObsidianNotesTool


@pytest.fixture(autouse=True)
def vault(tmp_path):
    from core.config import config

    # Config is a frozen dataclass singleton; bypass frozen=True for this test override.
    object.__setattr__(config, "obsidian_vault_path", str(tmp_path))
    yield tmp_path
    object.__setattr__(config, "obsidian_vault_path", None)


def test_create_note_writes_markdown_file(vault):
    result = CreateObsidianNoteTool().run(title="Meeting Notes", content="Discussed roadmap.")
    assert "Meeting Notes" in result

    note_path = vault / "Meeting Notes.md"
    assert note_path.exists()
    assert "Discussed roadmap." in note_path.read_text()


def test_create_note_sanitizes_filename(vault):
    CreateObsidianNoteTool().run(title="Q3: Report / Review", content="x")
    files = list(vault.glob("*.md"))
    assert len(files) == 1
    assert "/" not in files[0].name
    assert ":" not in files[0].name


def test_append_to_existing_note(vault):
    CreateObsidianNoteTool().run(title="Journal", content="Day 1.")
    AppendObsidianNoteTool().run(title="Journal", content="Day 2.")

    text = (vault / "Journal.md").read_text()
    assert "Day 1." in text
    assert "Day 2." in text


def test_append_to_missing_note_returns_friendly_error(vault):
    result = AppendObsidianNoteTool().run(title="Ghost", content="x")
    assert "No note named" in result


def test_list_notes_empty_vault(vault):
    result = ListObsidianNotesTool().run()
    assert "no notes yet" in result


def test_list_notes(vault):
    CreateObsidianNoteTool().run(title="Journal", content="x")
    CreateObsidianNoteTool().run(title="Meeting Notes", content="y")

    result = ListObsidianNotesTool().run()

    assert "- Journal" in result
    assert "- Meeting Notes" in result


def test_list_notes_filters_by_query(vault):
    CreateObsidianNoteTool().run(title="Journal", content="x")
    CreateObsidianNoteTool().run(title="Meeting Notes", content="y")

    result = ListObsidianNotesTool().run(query="meeting")

    assert "Meeting Notes" in result
    assert "Journal" not in result


def test_list_notes_no_match(vault):
    CreateObsidianNoteTool().run(title="Journal", content="x")
    result = ListObsidianNotesTool().run(query="nonexistent")
    assert "No matching notes" in result

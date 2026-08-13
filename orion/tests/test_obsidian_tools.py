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


def test_create_note_refuses_to_silently_overwrite_an_existing_one(vault):
    """Regression test: a second 'create a note called X' for a different,
    unrelated idea used to silently wipe out the first note's content with
    no error and no indication anything was overwritten."""
    CreateObsidianNoteTool().run(title="Ideas", content="Idea A.")

    result = CreateObsidianNoteTool().run(title="Ideas", content="Idea B.")

    assert "already exists" in result
    assert (vault / "Ideas.md").read_text().count("Idea A.") == 1
    assert "Idea B." not in (vault / "Ideas.md").read_text()


def test_create_note_overwrite_true_replaces_it(vault):
    CreateObsidianNoteTool().run(title="Ideas", content="Idea A.")

    result = CreateObsidianNoteTool().run(title="Ideas", content="Idea B.", overwrite=True)

    assert "Created" in result
    text = (vault / "Ideas.md").read_text()
    assert "Idea B." in text
    assert "Idea A." not in text


def test_create_note_tags_with_commas_and_colons_survive_as_separate_valid_tags(vault):
    """Regression test: tags were interpolated raw into YAML flow-sequence
    syntax — a tag containing a comma silently split into two tags on
    Obsidian's YAML parse, and one containing a colon could produce
    invalid YAML that keeps Obsidian from parsing the frontmatter at all."""
    CreateObsidianNoteTool().run(title="Tagged", content="x", tags=["type: idea", "work, urgent"])

    text = (vault / "Tagged.md").read_text()
    assert 'tags: ["type: idea", "work, urgent"]' in text

    import yaml

    frontmatter = text.split("---")[1]
    parsed = yaml.safe_load(frontmatter)
    assert parsed["tags"] == ["type: idea", "work, urgent"]


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

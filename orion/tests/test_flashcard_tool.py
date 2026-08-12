import pytest

from tools.flashcard_tool import GenerateClozeFlashcardsTool, GenerateFlashcardsTool, GenerateQuizTool


@pytest.fixture(autouse=True)
def in_tmp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_generate_flashcards_creates_apkg():
    result = GenerateFlashcardsTool().run(
        deck_name="French Vocab",
        cards=[{"question": "chat", "answer": "cat"}, {"question": "chien", "answer": "dog"}],
    )
    assert "2 flashcards" in result

    from pathlib import Path

    files = list(Path("outputs").glob("*.apkg"))
    assert len(files) == 1
    assert files[0].stat().st_size > 0


def test_generate_cloze_flashcards_creates_apkg():
    result = GenerateClozeFlashcardsTool().run(
        deck_name="Capitals",
        cards=[
            {"text": "The capital of France is {{c1::Paris}}.", "extra": "A European country."},
            {"text": "The capital of Japan is {{c1::Tokyo}}."},
        ],
    )
    assert "2 cloze flashcards" in result

    from pathlib import Path

    files = list(Path("outputs").glob("*.apkg"))
    assert len(files) == 1
    assert files[0].stat().st_size > 0


def test_generate_quiz_formats_text():
    result = GenerateQuizTool().run(
        title="Geography",
        questions=[{"question": "Capital of France?", "options": ["Lyon", "Paris"], "answer": "Paris"}],
    )
    assert "Geography" in result
    assert "Capital of France?" in result
    assert "Answer: Paris" in result

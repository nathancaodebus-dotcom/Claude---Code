"""Turn any content into study material: a real importable Anki deck
(.apkg via genanki) or a plain-text quiz. Claude writes the actual
question/answer pairs from whatever the user gives it; these tools just
package them."""
from __future__ import annotations

import random

import genanki

from core.attachments import push as push_attachment
from tools.base import Tool
from tools.document_utils import resolve_path, slugify

_BASIC_MODEL = genanki.Model(
    1607392319,
    "Orion Basic",
    fields=[{"name": "Question"}, {"name": "Answer"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Question}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Answer}}',
        }
    ],
)


class GenerateFlashcardsTool(Tool):
    name = "generate_flashcards"
    description = (
        "Generate an Anki-importable flashcard deck (.apkg) from a list of question/answer pairs "
        "you've written from the source material — e.g. after reading a document, extract the key "
        "facts as flashcards."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "deck_name": {"type": "string"},
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
                    "required": ["question", "answer"],
                },
            },
        },
        "required": ["deck_name", "cards"],
    }

    def run(self, deck_name: str, cards: list[dict]) -> str:
        deck_id = random.randrange(1 << 30, 1 << 31)
        deck = genanki.Deck(deck_id, deck_name)

        for card in cards:
            deck.add_note(genanki.Note(model=_BASIC_MODEL, fields=[card["question"], card["answer"]]))

        path = resolve_path(slugify(deck_name), "apkg")
        genanki.Package(deck).write_to_file(str(path))

        push_attachment(str(path))
        return f"Generated {len(cards)} flashcards in deck '{deck_name}', saved to {path}. Import it into Anki."


class GenerateQuizTool(Tool):
    name = "generate_quiz"
    description = "Format a set of quiz questions (with answers) as plain text, e.g. for self-testing on a topic."
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "answer": {"type": "string"},
                    },
                    "required": ["question", "answer"],
                },
            },
        },
        "required": ["title", "questions"],
    }

    def run(self, title: str, questions: list[dict]) -> str:
        lines = [f"# {title}", ""]
        for i, q in enumerate(questions, start=1):
            lines.append(f"{i}. {q['question']}")
            for option in q.get("options", []):
                lines.append(f"   - {option}")
            lines.append(f"   Answer: {q['answer']}")
            lines.append("")
        return "\n".join(lines)

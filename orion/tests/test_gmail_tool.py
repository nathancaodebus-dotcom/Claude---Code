import base64

from tools.gmail_tool import _extract_body


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_extract_body_from_a_flat_top_level_text_plain_part():
    message = {
        "snippet": "short preview",
        "payload": {"parts": [{"mimeType": "text/plain", "body": {"data": _b64("Hello world")}}]},
    }
    assert _extract_body(message) == "Hello world"


def test_extract_body_recurses_into_nested_multipart_mixed_then_alternative():
    """Regression test: any message with an attachment (or many client-
    generated HTML+plaintext emails) wraps the actual text one or more
    levels deep — payload -> multipart/mixed -> multipart/alternative ->
    text/plain — not as a direct top-level part. This used to silently
    fall back to the snippet for exactly this (very common) shape despite
    being documented as returning the full body."""
    message = {
        "snippet": "short preview",
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/html", "body": {"data": _b64("<p>Hi</p>")}},
                        {"mimeType": "text/plain", "body": {"data": _b64("The full body text")}},
                    ],
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "invoice.pdf",
                    "body": {"attachmentId": "abc123"},
                },
            ],
        },
    }
    assert _extract_body(message) == "The full body text"


def test_extract_body_falls_back_to_snippet_when_no_text_plain_part_exists():
    message = {
        "snippet": "short preview",
        "payload": {"mimeType": "multipart/alternative", "parts": [{"mimeType": "text/html", "body": {"data": _b64("<p>Hi</p>")}}]},
    }
    assert _extract_body(message) == "short preview"


def test_extract_body_falls_back_to_snippet_when_the_part_has_no_data():
    message = {
        "snippet": "short preview",
        "payload": {"mimeType": "text/plain", "body": {}},
    }
    assert _extract_body(message) == "short preview"

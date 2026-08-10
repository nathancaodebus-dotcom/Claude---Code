from tools.document_utils import slugify


def test_slugify_basic():
    assert slugify("My Deck") == "my-deck"


def test_slugify_strips_punctuation():
    assert slugify("Q3 Report: Sales & Growth!") == "q3-report-sales-growth"


def test_slugify_empty_falls_back():
    assert slugify("???") == "document"

import pytest

from tools.productivity_tools import parse_duration


def test_parse_duration_simple():
    assert parse_duration("10m") == 600
    assert parse_duration("1h") == 3600
    assert parse_duration("2 days") == 172800


def test_parse_duration_combined():
    assert parse_duration("1h30m") == 5400


def test_parse_duration_weeks():
    """Regression test: tools/project_tools.py's AddMilestoneTool documents
    its own in_duration parameter with 'e.g. '3 days', '2 weeks'', but the
    parser had no 'week' unit at all — following the tool's own documented
    example raised a ValueError before any milestone was created."""
    assert parse_duration("2 weeks") == 1209600
    assert parse_duration("1 week") == 604800
    assert parse_duration("3w") == 1814400


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        parse_duration("whenever")

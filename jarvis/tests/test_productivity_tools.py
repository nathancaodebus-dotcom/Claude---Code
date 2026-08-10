import pytest

from tools.productivity_tools import parse_duration


def test_parse_duration_simple():
    assert parse_duration("10m") == 600
    assert parse_duration("1h") == 3600
    assert parse_duration("2 days") == 172800


def test_parse_duration_combined():
    assert parse_duration("1h30m") == 5400


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        parse_duration("whenever")

import math

import pytest

from tools.utility_tools import (
    CalculatorTool,
    GeneratePasswordTool,
    GenerateQrCodeTool,
    UnitConversionTool,
    safe_eval,
)


def test_safe_eval_arithmetic():
    assert safe_eval("2 + 3 * 4") == 14
    assert safe_eval("(2 + 3) * 4") == 20
    assert safe_eval("2 ** 10") == 1024
    assert math.isclose(safe_eval("sqrt(2)"), math.sqrt(2))
    assert safe_eval("-5 + 2") == -3


def test_safe_eval_rejects_arbitrary_code():
    with pytest.raises(Exception):
        safe_eval("__import__('os').system('echo hi')")
    with pytest.raises(Exception):
        safe_eval("open('/etc/passwd')")


def test_generate_qr_code_uses_a_collision_resistant_filename(tmp_path, monkeypatch):
    """Regression test: filenames used to be derived from
    abs(hash(text)) % 100000 — a 100k-bucket space where two different
    texts collide fairly easily (birthday-paradox odds cross 50% at only
    ~370 QR codes generated in one process), silently overwriting each
    other's saved file. Generating several distinct QR codes should never
    reuse a filename."""
    monkeypatch.chdir(tmp_path)
    tool = GenerateQrCodeTool()

    paths = []
    for i in range(20):
        result = tool.run(text=f"https://example.com/{i}")
        paths.append(result.split("saved to ")[1].rstrip("."))

    assert len(set(paths)) == 20


def test_calculator_tool():
    result = CalculatorTool().run("2 + 2")
    assert "4" in result


def test_unit_conversion_length():
    result = UnitConversionTool().run(value=1, from_unit="km", to_unit="m")
    assert "1000" in result


def test_unit_conversion_temperature():
    result = UnitConversionTool().run(value=0, from_unit="c", to_unit="f")
    assert "32" in result


def test_unit_conversion_rejects_mismatched_categories():
    with pytest.raises(ValueError):
        UnitConversionTool().run(value=1, from_unit="kg", to_unit="km")


def test_generate_password_length_and_charset():
    password = GeneratePasswordTool().run(length=32, include_symbols=False)
    assert len(password) == 32
    assert all(c.isalnum() for c in password)

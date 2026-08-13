import builtins
import importlib

import pytest


@pytest.fixture
def utility_tools_without_qrcode(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "qrcode":
            raise ImportError("No module named 'qrcode'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    import tools.utility_tools as utility_tools_module

    module = importlib.reload(utility_tools_module)
    yield module
    importlib.reload(module)  # restore the real qrcode-backed module for other tests


def test_module_imports_without_qrcode(utility_tools_without_qrcode):
    assert utility_tools_without_qrcode.qrcode is None


def test_calculator_unaffected_by_missing_qrcode(utility_tools_without_qrcode):
    result = utility_tools_without_qrcode.CalculatorTool().run(expression="2 + 2")
    assert "4" in result


def test_unit_conversion_unaffected_by_missing_qrcode(utility_tools_without_qrcode):
    result = utility_tools_without_qrcode.UnitConversionTool().run(value=1, from_unit="km", to_unit="m")
    assert "1000" in result


def test_password_generator_unaffected_by_missing_qrcode(utility_tools_without_qrcode):
    result = utility_tools_without_qrcode.GeneratePasswordTool().run(length=16)
    assert len(result) == 16


def test_qr_code_degrades_gracefully(utility_tools_without_qrcode):
    result = utility_tools_without_qrcode.GenerateQrCodeTool().run(text="hello")
    assert "not installed" in result

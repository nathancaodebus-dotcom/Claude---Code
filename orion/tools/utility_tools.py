"""Small self-contained utilities: calculator, unit conversion, password
generation, QR code generation. No network required."""
from __future__ import annotations

import ast
import math
import operator
import secrets
import string
from pathlib import Path

from core.attachments import push as push_attachment
from tools.base import Tool

try:
    import qrcode
except ImportError:
    # qrcode[pil] pulls in Pillow, which needs system jpeg/zlib headers to
    # build from source and can fail on some platforms — degrade just this
    # one tool instead of losing the calculator/converter/password tools too.
    qrcode = None

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    "sqrt": math.sqrt, "abs": abs, "round": round,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log, "log10": math.log10,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}


def _eval_node(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
        args = [_eval_node(a) for a in node.args]
        return _FUNCTIONS[node.func.id](*args)
    raise ValueError("Expression contains something that isn't a basic arithmetic operation.")


def safe_eval(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree)


_LENGTH_TO_METERS = {
    "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
    "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
}
_WEIGHT_TO_GRAMS = {"mg": 0.001, "g": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592}


class CalculatorTool(Tool):
    name = "calculate"
    description = (
        "Evaluate a math expression, e.g. '12 * (3 + 4)', 'sqrt(2)', '2**10'. "
        "Supports + - * / // % **, parentheses, and sqrt/abs/round/sin/cos/tan/log/log10."
    )
    input_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    }

    def run(self, expression: str) -> str:
        result = safe_eval(expression)
        return f"{expression} = {result}"


class UnitConversionTool(Tool):
    name = "convert_units"
    description = (
        "Convert a value between units of length (mm, cm, m, km, in, ft, yd, mi), "
        "weight (mg, g, kg, oz, lb), or temperature (c, f, k)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "value": {"type": "number"},
            "from_unit": {"type": "string"},
            "to_unit": {"type": "string"},
        },
        "required": ["value", "from_unit", "to_unit"],
    }

    def run(self, value: float, from_unit: str, to_unit: str) -> str:
        from_unit, to_unit = from_unit.lower(), to_unit.lower()

        if from_unit in _LENGTH_TO_METERS and to_unit in _LENGTH_TO_METERS:
            result = value * _LENGTH_TO_METERS[from_unit] / _LENGTH_TO_METERS[to_unit]
        elif from_unit in _WEIGHT_TO_GRAMS and to_unit in _WEIGHT_TO_GRAMS:
            result = value * _WEIGHT_TO_GRAMS[from_unit] / _WEIGHT_TO_GRAMS[to_unit]
        elif {from_unit, to_unit} <= {"c", "f", "k"}:
            result = self._convert_temperature(value, from_unit, to_unit)
        else:
            raise ValueError(f"Don't know how to convert '{from_unit}' to '{to_unit}'.")

        return f"{value} {from_unit} = {round(result, 4)} {to_unit}"

    @staticmethod
    def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
        celsius = {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[from_unit]
        return {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[to_unit]


class GeneratePasswordTool(Tool):
    name = "generate_password"
    description = "Generate a cryptographically random password."
    input_schema = {
        "type": "object",
        "properties": {
            "length": {"type": "integer", "description": "Default 20."},
            "include_symbols": {"type": "boolean", "description": "Default true."},
        },
    }

    def run(self, length: int = 20, include_symbols: bool = True) -> str:
        alphabet = string.ascii_letters + string.digits
        if include_symbols:
            alphabet += "!@#$%^&*()-_=+"
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        return password


class GenerateQrCodeTool(Tool):
    name = "generate_qr_code"
    description = "Generate a QR code image encoding the given text (a URL, wifi password, anything)."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, text: str) -> str:
        if qrcode is None:
            return "qrcode/Pillow is not installed — QR code generation isn't available here."
        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)
        path = output_dir / f"qr_{abs(hash(text)) % 100000}.png"

        img = qrcode.make(text)
        img.save(path)
        push_attachment(str(path))
        return f"QR code generated and saved to {path}."

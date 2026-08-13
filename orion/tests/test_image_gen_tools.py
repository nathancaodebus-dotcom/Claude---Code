import base64

import pytest

from tools.image_gen_tools import GenerateImageTool


class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


# A 1x1 transparent PNG, just enough bytes to prove round-tripping works.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_generate_image_saves_the_decoded_png(monkeypatch, output_dir):
    monkeypatch.setattr(
        "tools.image_gen_tools.client.post",
        lambda *a, **kw: _FakeResponse(
            200,
            {"predictions": [{"bytesBase64Encoded": base64.b64encode(_TINY_PNG).decode()}]},
        ),
    )

    result = GenerateImageTool().run(prompt="a small red dot")

    assert "Generated image saved to" in result
    saved = list((output_dir / "outputs" / "images").glob("*.png"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == _TINY_PNG


def test_generate_image_uses_file_name_when_given(monkeypatch, output_dir):
    monkeypatch.setattr(
        "tools.image_gen_tools.client.post",
        lambda *a, **kw: _FakeResponse(
            200,
            {"predictions": [{"bytesBase64Encoded": base64.b64encode(_TINY_PNG).decode()}]},
        ),
    )

    GenerateImageTool().run(prompt="a cat wearing a hat", file_name="my custom name")

    assert (output_dir / "outputs" / "images" / "my-custom-name.png").exists()


def test_generate_image_reports_http_errors(monkeypatch, output_dir):
    monkeypatch.setattr(
        "tools.image_gen_tools.client.post",
        lambda *a, **kw: _FakeResponse(429, text="quota exceeded"),
    )

    result = GenerateImageTool().run(prompt="anything")

    assert "failed" in result
    assert "429" in result
    assert not (output_dir / "outputs" / "images").exists()


def test_generate_image_handles_missing_predictions(monkeypatch, output_dir):
    monkeypatch.setattr(
        "tools.image_gen_tools.client.post", lambda *a, **kw: _FakeResponse(200, {"predictions": []})
    )

    result = GenerateImageTool().run(prompt="anything")

    assert "no image" in result


def test_generate_image_count_saves_multiple_numbered_files(monkeypatch, output_dir):
    monkeypatch.setattr(
        "tools.image_gen_tools.client.post",
        lambda *a, **kw: _FakeResponse(
            200,
            {
                "predictions": [
                    {"bytesBase64Encoded": base64.b64encode(_TINY_PNG).decode()},
                    {"bytesBase64Encoded": base64.b64encode(_TINY_PNG).decode()},
                    {"bytesBase64Encoded": base64.b64encode(_TINY_PNG).decode()},
                ]
            },
        ),
    )

    result = GenerateImageTool().run(prompt="a small red dot", count=3, file_name="dot")

    assert "Generated 3 images" in result
    saved = sorted(p.name for p in (output_dir / "outputs" / "images").glob("*.png"))
    assert saved == ["dot-1.png", "dot-2.png", "dot-3.png"]


def test_generate_image_count_is_clamped_to_valid_range(monkeypatch, output_dir):
    captured = {}

    def fake_post(url, params, json, timeout):
        captured["sampleCount"] = json["parameters"]["sampleCount"]
        return _FakeResponse(200, {"predictions": [{"bytesBase64Encoded": base64.b64encode(_TINY_PNG).decode()}]})

    monkeypatch.setattr("tools.image_gen_tools.client.post", fake_post)

    GenerateImageTool().run(prompt="anything", count=99)

    assert captured["sampleCount"] == 4

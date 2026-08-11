from pathlib import Path

import pytest
from PIL import Image

from tools.image_edit_tools import AddTextToImageTool, EditImageTool


@pytest.fixture
def source_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "source.png"
    Image.new("RGB", (100, 60), color=(200, 50, 50)).save(path)
    return path


def test_resize(source_image):
    result = EditImageTool().run(path=str(source_image), operation="resize", width=20, height=10)
    assert "Applied 'resize'" in result
    out_path = source_image.parent / "outputs" / "images" / "source-resize.png"
    assert Image.open(out_path).size == (20, 10)


def test_resize_requires_both_dimensions(source_image):
    result = EditImageTool().run(path=str(source_image), operation="resize", width=20)
    assert "needs both width and height" in result


def test_crop(source_image):
    result = EditImageTool().run(path=str(source_image), operation="crop", box=[0, 0, 40, 30])
    assert "Applied 'crop'" in result
    out_path = source_image.parent / "outputs" / "images" / "source-crop.png"
    assert Image.open(out_path).size == (40, 30)


def test_crop_requires_a_valid_box(source_image):
    result = EditImageTool().run(path=str(source_image), operation="crop", box=[0, 0])
    assert "needs box=" in result


def test_rotate_with_expand_changes_dimensions(source_image):
    EditImageTool().run(path=str(source_image), operation="rotate", angle=90)
    out_path = source_image.parent / "outputs" / "images" / "source-rotate.png"
    # A 100x60 image rotated 90 degrees with expand=True becomes ~60x100.
    assert Image.open(out_path).size == (60, 100)


def test_grayscale(source_image):
    EditImageTool().run(path=str(source_image), operation="grayscale")
    out_path = source_image.parent / "outputs" / "images" / "source-grayscale.png"
    assert Image.open(out_path).mode == "L"


def test_adjust_brightness_darkens_pixels(source_image):
    EditImageTool().run(path=str(source_image), operation="adjust", brightness=0.2)
    out_path = source_image.parent / "outputs" / "images" / "source-adjust.png"
    r, g, b = Image.open(out_path).getpixel((0, 0))
    assert r < 200  # original red channel was 200; darkened should be lower


def test_unknown_operation(source_image):
    result = EditImageTool().run(path=str(source_image), operation="teleport")
    assert "Unknown operation" in result


def test_missing_source_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = EditImageTool().run(path="does-not-exist.png", operation="grayscale")
    assert "is not a file" in result


def test_custom_output_path_is_respected(source_image, tmp_path):
    custom = tmp_path / "custom" / "out.png"
    EditImageTool().run(path=str(source_image), operation="grayscale", output_path=str(custom))
    assert custom.exists()


def test_jpeg_output_flattens_alpha(source_image, tmp_path):
    """RGBA can't be saved as JPEG — this must not crash."""
    out_path = tmp_path / "out.jpg"
    result = EditImageTool().run(path=str(source_image), operation="grayscale", output_path=str(out_path))
    assert "Applied" in result
    assert out_path.exists()


def test_add_text_to_image_produces_a_file(source_image):
    result = AddTextToImageTool().run(path=str(source_image), text="Hello")
    assert "Added text" in result
    out_path = source_image.parent / "outputs" / "images" / "source-text.png"
    assert out_path.exists()


def test_add_text_to_image_missing_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = AddTextToImageTool().run(path="nope.png", text="Hello")
    assert "is not a file" in result

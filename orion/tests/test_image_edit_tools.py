from pathlib import Path

import pytest
from PIL import Image

from tools.image_edit_tools import AddTextToImageTool, CreateImageCollageTool, EditImageTool


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


def test_sepia(source_image):
    result = EditImageTool().run(path=str(source_image), operation="sepia")
    assert "Applied 'sepia'" in result
    out_path = source_image.parent / "outputs" / "images" / "source-sepia.png"
    img = Image.open(out_path)
    r, g, b = img.convert("RGB").getpixel((0, 0))
    assert r > b  # sepia is warm-toned: more red than blue


def test_invert(source_image):
    original = Image.open(source_image).convert("RGB").getpixel((0, 0))
    result = EditImageTool().run(path=str(source_image), operation="invert")
    assert "Applied 'invert'" in result
    out_path = source_image.parent / "outputs" / "images" / "source-invert.png"
    inverted = Image.open(out_path).convert("RGB").getpixel((0, 0))
    assert inverted == tuple(255 - c for c in original)


def test_invert_preserves_alpha(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "rgba.png"
    Image.new("RGBA", (10, 10), color=(100, 150, 200, 128)).save(path)

    EditImageTool().run(path=str(path), operation="invert")

    out_path = tmp_path / "outputs" / "images" / "rgba-invert.png"
    r, g, b, a = Image.open(out_path).getpixel((0, 0))
    assert a == 128
    assert (r, g, b) == (155, 105, 55)


def test_create_image_collage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = []
    for i, color in enumerate(["red", "green", "blue"]):
        p = tmp_path / f"img{i}.png"
        Image.new("RGB", (50, 50), color=color).save(p)
        paths.append(str(p))

    result = CreateImageCollageTool().run(paths=paths, cell_size=100)

    assert "3 images" in result
    out_files = list((tmp_path / "outputs" / "images").glob("*collage*"))
    assert len(out_files) == 1
    collage = Image.open(out_files[0])
    assert collage.size[0] % 100 == 0
    assert collage.size[1] % 100 == 0


def test_create_image_collage_requires_at_least_two(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "img.png"
    Image.new("RGB", (10, 10)).save(p)

    result = CreateImageCollageTool().run(paths=[str(p)])
    assert "at least 2" in result


def test_create_image_collage_missing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "img.png"
    Image.new("RGB", (10, 10)).save(p)

    result = CreateImageCollageTool().run(paths=[str(p), "nope.png"])
    assert "Not found" in result

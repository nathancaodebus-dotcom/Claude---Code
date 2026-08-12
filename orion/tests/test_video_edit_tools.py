import subprocess
from pathlib import Path

import pytest

from tools.video_edit_tools import (
    AddAudioToVideoTool,
    AddCaptionToVideoTool,
    AddWatermarkToVideoTool,
    ChangeVideoSpeedTool,
    ConcatenateVideosTool,
    ConvertVideoFormatTool,
    ExtractAudioFromVideoTool,
    ExtractVideoFrameTool,
    TrimVideoTool,
)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _touch(path: Path) -> Path:
    path.write_bytes(b"fake video bytes")
    return path


def _mock_ffmpeg_success(monkeypatch):
    def fake_run(cmd, **kwargs):
        # Write a placeholder file at whatever path ffmpeg was told to
        # produce (always the last argument in every tool here).
        Path(cmd[-1]).write_bytes(b"fake output")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_trim_video_missing_source(workdir):
    result = TrimVideoTool().run(path="nope.mp4", start_seconds=0, duration_seconds=5)
    assert "is not a file" in result


def test_trim_video_success(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")
    _mock_ffmpeg_success(monkeypatch)

    result = TrimVideoTool().run(path=str(source), start_seconds=2, duration_seconds=5)

    assert "Trimmed" in result
    assert (workdir / "outputs" / "videos" / "clip-trim.mp4").exists()


def test_trim_video_reports_ffmpeg_not_installed(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("no ffmpeg")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = TrimVideoTool().run(path=str(source), start_seconds=0, duration_seconds=5)

    assert "ffmpeg is not installed" in result


def test_trim_video_reports_ffmpeg_failure(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr=b"invalid codec")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = TrimVideoTool().run(path=str(source), start_seconds=0, duration_seconds=5)

    assert "ffmpeg failed" in result
    assert "invalid codec" in result


def test_trim_video_reports_timeout(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 300)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = TrimVideoTool().run(path=str(source), start_seconds=0, duration_seconds=5)

    assert "timed out" in result


def test_concatenate_requires_at_least_two_videos(workdir):
    source = _touch(workdir / "clip.mp4")
    result = ConcatenateVideosTool().run(paths=[str(source)])
    assert "at least 2" in result


def test_concatenate_reports_missing_files(workdir):
    source = _touch(workdir / "clip.mp4")
    result = ConcatenateVideosTool().run(paths=[str(source), "missing.mp4"])
    assert "Not found" in result
    assert "missing.mp4" in result


def test_concatenate_success(workdir, monkeypatch):
    a = _touch(workdir / "a.mp4")
    b = _touch(workdir / "b.mp4")
    _mock_ffmpeg_success(monkeypatch)

    result = ConcatenateVideosTool().run(paths=[str(a), str(b)])

    assert "Concatenated 2 videos" in result
    assert (workdir / "outputs" / "videos" / "a-concat.mp4").exists()


def test_extract_audio_success(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")
    _mock_ffmpeg_success(monkeypatch)

    result = ExtractAudioFromVideoTool().run(path=str(source))

    assert "Extracted audio" in result
    assert (workdir / "outputs" / "videos" / "clip-audio.mp3").exists()


def test_add_audio_to_video_missing_files(workdir):
    result = AddAudioToVideoTool().run(video_path="nope.mp4", audio_path="also-nope.mp3")
    assert "is not a file" in result


def test_add_audio_to_video_success(workdir, monkeypatch):
    video = _touch(workdir / "clip.mp4")
    audio = _touch(workdir / "music.mp3")
    _mock_ffmpeg_success(monkeypatch)

    result = AddAudioToVideoTool().run(video_path=str(video), audio_path=str(audio))

    assert "Replaced the audio" in result
    assert (workdir / "outputs" / "videos" / "clip-dubbed.mp4").exists()


def test_convert_video_format_uses_requested_extension(workdir, monkeypatch):
    source = _touch(workdir / "clip.mov")
    _mock_ffmpeg_success(monkeypatch)

    result = ConvertVideoFormatTool().run(path=str(source), format="mp4")

    assert "Converted" in result
    assert (workdir / "outputs" / "videos" / "clip-converted.mp4").exists()


def test_add_caption_to_video_success(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")
    _mock_ffmpeg_success(monkeypatch)

    result = AddCaptionToVideoTool().run(path=str(source), text="Hello, world!")

    assert "Added a caption" in result
    assert (workdir / "outputs" / "videos" / "clip-caption.mp4").exists()


def test_add_caption_escapes_special_characters(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"fake output")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    AddCaptionToVideoTool().run(path=str(source), text="it's 5:00")

    drawtext_arg = captured["cmd"][captured["cmd"].index("-vf") + 1]
    assert "it\\'s 5\\:00" in drawtext_arg


def test_custom_output_path_is_respected(workdir, monkeypatch, tmp_path):
    source = _touch(workdir / "clip.mp4")
    _mock_ffmpeg_success(monkeypatch)
    custom = tmp_path / "somewhere" / "out.mp4"

    TrimVideoTool().run(path=str(source), start_seconds=0, duration_seconds=1, output_path=str(custom))

    assert custom.exists()


def test_add_watermark_missing_files(workdir):
    result = AddWatermarkToVideoTool().run(video_path="nope.mp4", image_path="also-nope.png")
    assert "is not a file" in result


def test_add_watermark_success(workdir, monkeypatch):
    video = _touch(workdir / "clip.mp4")
    (workdir / "logo.png").write_bytes(b"fake png bytes")
    _mock_ffmpeg_success(monkeypatch)

    result = AddWatermarkToVideoTool().run(video_path=str(video), image_path=str(workdir / "logo.png"))

    assert "Added watermark" in result
    assert (workdir / "outputs" / "videos" / "clip-watermarked.mp4").exists()


def test_add_watermark_position_maps_to_overlay_filter(workdir, monkeypatch):
    video = _touch(workdir / "clip.mp4")
    (workdir / "logo.png").write_bytes(b"fake png bytes")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"fake output")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    AddWatermarkToVideoTool().run(
        video_path=str(video), image_path=str(workdir / "logo.png"), position="top-left"
    )

    filter_arg = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert filter_arg == "overlay=10:10"


def test_change_video_speed_success(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")
    _mock_ffmpeg_success(monkeypatch)

    result = ChangeVideoSpeedTool().run(path=str(source), speed_factor=2.0)

    assert "2.0x" in result
    assert (workdir / "outputs" / "videos" / "clip-speed.mp4").exists()


def test_change_video_speed_clamps_out_of_range_values(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")
    _mock_ffmpeg_success(monkeypatch)

    result = ChangeVideoSpeedTool().run(path=str(source), speed_factor=10.0)

    assert "2.0x" in result


def test_extract_video_frame_success(workdir, monkeypatch):
    source = _touch(workdir / "clip.mp4")
    _mock_ffmpeg_success(monkeypatch)

    result = ExtractVideoFrameTool().run(path=str(source), at_seconds=3.5)

    assert "Extracted the frame" in result
    assert (workdir / "outputs" / "videos" / "clip-frame.png").exists()


def test_extract_video_frame_missing_source(workdir):
    result = ExtractVideoFrameTool().run(path="nope.mp4")
    assert "is not a file" in result

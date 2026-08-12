"""Edit video files — trim, concatenate, extract/replace audio, convert
format, and burn in text captions — via the `ffmpeg` command-line tool
(already required for Telegram voice replies; see README). No extra Python
dependency to fail installing on Termux/a Pi, but ffmpeg itself is a system
package (`apt install ffmpeg` / `brew install ffmpeg`) — every tool here
degrades to a clear message instead of a stack trace if it isn't found,
same pattern as interfaces/telegram_bot.py's voice-reply encoding.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from core.attachments import push as push_attachment
from tools.base import Tool

OUTPUT_DIR = Path("outputs") / "videos"
_TIMEOUT_S = 300  # encoding can take a while, unlike everything else in this project


def _output_path(source_path: str, suffix: str, output_path: str | None, extension: str | None = None) -> Path:
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        return Path(output_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ext = extension or Path(source_path).suffix.lstrip(".") or "mp4"
    return OUTPUT_DIR / f"{Path(source_path).stem}-{suffix}.{ext}"


def _run_ffmpeg(args: list[str]) -> str | None:
    """Runs ffmpeg with the given args (excluding the binary name and -y).
    Returns None on success, or a user-facing error message on failure."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", *args],
            capture_output=True,
            timeout=_TIMEOUT_S,
            check=True,
        )
    except FileNotFoundError:
        return "ffmpeg is not installed — video editing needs it (`apt install ffmpeg` / `brew install ffmpeg`)."
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        return f"ffmpeg failed: {stderr[-500:]}"
    except subprocess.TimeoutExpired:
        return f"ffmpeg timed out after {_TIMEOUT_S}s — the file may be too large/long."
    return None


class TrimVideoTool(Tool):
    name = "trim_video"
    description = "Cut a video to a specific time range, re-encoded into a clean standalone clip."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_seconds": {"type": "number"},
            "duration_seconds": {"type": "number"},
            "output_path": {"type": "string"},
        },
        "required": ["path", "start_seconds", "duration_seconds"],
    }

    def run(self, path: str, start_seconds: float, duration_seconds: float, output_path: str | None = None) -> str:
        if not Path(path).is_file():
            return f"'{path}' is not a file."
        out_path = _output_path(path, "trim", output_path)
        error = _run_ffmpeg(
            ["-i", path, "-ss", str(start_seconds), "-t", str(duration_seconds), str(out_path)]
        )
        if error:
            return error
        push_attachment(str(out_path))
        return f"Trimmed '{path}' to {duration_seconds}s starting at {start_seconds}s, saved to {out_path}."


class ConcatenateVideosTool(Tool):
    name = "concatenate_videos"
    description = (
        "Join multiple video files into one, in the given order. Re-encodes for reliability, so "
        "inputs don't need matching formats — but each input needs both a video and an audio track."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "At least 2 video paths, in the order they should play.",
            },
            "output_path": {"type": "string"},
        },
        "required": ["paths"],
    }

    def run(self, paths: list[str], output_path: str | None = None) -> str:
        if len(paths) < 2:
            return "Need at least 2 videos to concatenate."
        missing = [p for p in paths if not Path(p).is_file()]
        if missing:
            return f"Not found: {', '.join(missing)}"

        out_path = _output_path(paths[0], "concat", output_path)
        inputs: list[str] = []
        for p in paths:
            inputs += ["-i", p]
        stream_pairs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(paths)))
        filter_complex = f"{stream_pairs}concat=n={len(paths)}:v=1:a=1[outv][outa]"

        error = _run_ffmpeg(
            [*inputs, "-filter_complex", filter_complex, "-map", "[outv]", "-map", "[outa]", str(out_path)]
        )
        if error:
            return error
        push_attachment(str(out_path))
        return f"Concatenated {len(paths)} videos into {out_path}."


class ExtractAudioFromVideoTool(Tool):
    name = "extract_audio_from_video"
    description = "Extract a video's audio track as a standalone MP3 file."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "output_path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, path: str, output_path: str | None = None) -> str:
        if not Path(path).is_file():
            return f"'{path}' is not a file."
        out_path = _output_path(path, "audio", output_path, extension="mp3")
        error = _run_ffmpeg(["-i", path, "-vn", "-acodec", "libmp3lame", str(out_path)])
        if error:
            return error
        push_attachment(str(out_path))
        return f"Extracted audio from '{path}' to {out_path}."


class AddAudioToVideoTool(Tool):
    name = "add_audio_to_video"
    description = "Replace a video's audio track with a different audio file (background music, a voiceover, ...)."
    input_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": "string"},
            "audio_path": {"type": "string"},
            "output_path": {"type": "string"},
        },
        "required": ["video_path", "audio_path"],
    }

    def run(self, video_path: str, audio_path: str, output_path: str | None = None) -> str:
        if not Path(video_path).is_file():
            return f"'{video_path}' is not a file."
        if not Path(audio_path).is_file():
            return f"'{audio_path}' is not a file."
        out_path = _output_path(video_path, "dubbed", output_path)
        error = _run_ffmpeg(
            [
                "-i", video_path, "-i", audio_path,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-shortest",
                str(out_path),
            ]
        )
        if error:
            return error
        push_attachment(str(out_path))
        return f"Replaced the audio in '{video_path}' with '{audio_path}', saved to {out_path}."


class ConvertVideoFormatTool(Tool):
    name = "convert_video_format"
    description = "Convert a video to a different container/format, e.g. .mov to .mp4."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "format": {"type": "string", "description": "Target extension, e.g. 'mp4', 'webm', 'mov'."},
            "output_path": {"type": "string"},
        },
        "required": ["path", "format"],
    }

    def run(self, path: str, format: str, output_path: str | None = None) -> str:  # noqa: A002
        if not Path(path).is_file():
            return f"'{path}' is not a file."
        out_path = _output_path(path, "converted", output_path, extension=format.lstrip("."))
        error = _run_ffmpeg(["-i", path, str(out_path)])
        if error:
            return error
        push_attachment(str(out_path))
        return f"Converted '{path}' to {out_path}."


class AddWatermarkToVideoTool(Tool):
    name = "add_watermark_to_video"
    description = "Overlay an image (a logo or watermark) onto a video, in a corner or centered."
    input_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": "string"},
            "image_path": {"type": "string"},
            "position": {
                "type": "string",
                "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"],
                "description": "Default 'bottom-right'.",
            },
            "output_path": {"type": "string"},
        },
        "required": ["video_path", "image_path"],
    }

    def run(self, video_path: str, image_path: str, position: str = "bottom-right", output_path: str | None = None) -> str:
        if not Path(video_path).is_file():
            return f"'{video_path}' is not a file."
        if not Path(image_path).is_file():
            return f"'{image_path}' is not a file."

        positions = {
            "top-left": "10:10",
            "top-right": "W-w-10:10",
            "bottom-left": "10:H-h-10",
            "bottom-right": "W-w-10:H-h-10",
            "center": "(W-w)/2:(H-h)/2",
        }
        out_path = _output_path(video_path, "watermarked", output_path)
        error = _run_ffmpeg(
            ["-i", video_path, "-i", image_path, "-filter_complex", f"overlay={positions[position]}", str(out_path)]
        )
        if error:
            return error
        push_attachment(str(out_path))
        return f"Added watermark to '{video_path}', saved to {out_path}."


class ChangeVideoSpeedTool(Tool):
    name = "change_video_speed"
    description = "Speed up or slow down a video (and its audio pitch stays natural), e.g. 2.0 for double speed, 0.5 for half speed."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "speed_factor": {
                "type": "number",
                "description": "Between 0.5 and 2.0. Values outside that range are clamped.",
            },
            "output_path": {"type": "string"},
        },
        "required": ["path", "speed_factor"],
    }

    def run(self, path: str, speed_factor: float, output_path: str | None = None) -> str:
        if not Path(path).is_file():
            return f"'{path}' is not a file."
        speed_factor = max(0.5, min(speed_factor, 2.0))
        out_path = _output_path(path, "speed", output_path)
        error = _run_ffmpeg(
            [
                "-i", path,
                "-filter_complex", f"[0:v]setpts={1 / speed_factor}*PTS[v];[0:a]atempo={speed_factor}[a]",
                "-map", "[v]", "-map", "[a]",
                str(out_path),
            ]
        )
        if error:
            return error
        push_attachment(str(out_path))
        return f"Changed the speed of '{path}' by {speed_factor}x, saved to {out_path}."


class ExtractVideoFrameTool(Tool):
    name = "extract_video_frame"
    description = "Grab a single frame from a video as a still image (e.g. for a thumbnail)."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "at_seconds": {"type": "number", "description": "Timestamp to grab the frame from. Default 0."},
            "output_path": {"type": "string"},
        },
        "required": ["path"],
    }

    def run(self, path: str, at_seconds: float = 0, output_path: str | None = None) -> str:
        if not Path(path).is_file():
            return f"'{path}' is not a file."
        out_path = _output_path(path, "frame", output_path, extension="png")
        error = _run_ffmpeg(["-ss", str(at_seconds), "-i", path, "-frames:v", "1", str(out_path)])
        if error:
            return error
        push_attachment(str(out_path))
        return f"Extracted the frame at {at_seconds}s from '{path}', saved to {out_path}."


class AddCaptionToVideoTool(Tool):
    name = "add_caption_to_video"
    description = "Burn a text caption permanently onto a video (not a toggleable subtitle track)."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "text": {"type": "string"},
            "position": {"type": "string", "enum": ["top", "bottom"], "description": "Default 'bottom'."},
            "font_size": {"type": "integer", "description": "Default 32."},
            "output_path": {"type": "string"},
        },
        "required": ["path", "text"],
    }

    def run(
        self, path: str, text: str, position: str = "bottom", font_size: int = 32, output_path: str | None = None
    ) -> str:
        if not Path(path).is_file():
            return f"'{path}' is not a file."
        out_path = _output_path(path, "caption", output_path)
        y_expr = "h-th-30" if position == "bottom" else "30"
        escaped_text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        drawtext = (
            f"drawtext=text='{escaped_text}':fontsize={font_size}:fontcolor=white:"
            f"borderw=2:bordercolor=black:x=(w-tw)/2:y={y_expr}"
        )
        error = _run_ffmpeg(["-i", path, "-vf", drawtext, str(out_path)])
        if error:
            return error
        push_attachment(str(out_path))
        return f"Added a caption to '{path}', saved to {out_path}."

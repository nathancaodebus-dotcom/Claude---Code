import subprocess
import wave
from pathlib import Path

import pytest

from interfaces.telegram_bot import _synthesize_to_ogg_opus


class FakeSynth:
    sample_rate = 22050

    def synthesize(self, text, urgent=False):
        return bytes(1000)  # 500 silent 16-bit samples, as raw PCM bytes


def test_returns_none_when_ffmpeg_missing(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("ffmpeg not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _synthesize_to_ogg_opus(FakeSynth(), "hello") is None


def test_returns_none_on_ffmpeg_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _synthesize_to_ogg_opus(FakeSynth(), "hello") is None


def test_returns_none_on_timeout(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _synthesize_to_ogg_opus(FakeSynth(), "hello") is None


def test_returns_bytes_when_ffmpeg_succeeds(monkeypatch):
    def fake_run(cmd, **kwargs):
        # cmd[-1] is the output ogg path — simulate ffmpeg having written to it.
        Path(cmd[-1]).write_bytes(b"fake-ogg-opus-data")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _synthesize_to_ogg_opus(FakeSynth(), "hello")
    assert result == b"fake-ogg-opus-data"


def test_writes_valid_wav_before_encoding(monkeypatch, tmp_path):
    captured_wav = {}

    def fake_run(cmd, **kwargs):
        wav_path = Path(cmd[cmd.index("-i") + 1])
        with wave.open(str(wav_path), "rb") as f:
            captured_wav["channels"] = f.getnchannels()
            captured_wav["rate"] = f.getframerate()
        Path(cmd[-1]).write_bytes(b"ok")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    _synthesize_to_ogg_opus(FakeSynth(), "hello")

    assert captured_wav["channels"] == 1
    assert captured_wav["rate"] == 22050

"""Synthesize ambient noise (white/pink/brown) locally for focus or sleep —
no external sound library or asset download needed, it's generated
on the fly with numpy and saved as a WAV file."""
from __future__ import annotations

import wave
from pathlib import Path

from core.attachments import push as push_attachment
from tools.base import Tool

try:
    import numpy as np
except ImportError:
    # numpy has no prebuilt wheel for Termux/Android (Bionic, not manylinux)
    # and building it from source needs a full C/Fortran/BLAS toolchain —
    # degrade this tool instead of taking the whole registry down with it.
    np = None

SAMPLE_RATE = 44100
MAX_DURATION_S = 600
_NUMPY_MISSING_MSG = (
    "numpy is not installed (it has no prebuilt wheel for Termux/Android and is heavy to "
    "build from source there) — ambient sound generation isn't available here."
)


def _white_noise(n_samples: int) -> np.ndarray:
    return np.random.normal(0, 1, n_samples)


def _pink_noise(n_samples: int) -> np.ndarray:
    white = np.random.normal(0, 1, n_samples)
    spectrum = np.fft.rfft(white)
    frequencies = np.fft.rfftfreq(n_samples)
    frequencies[0] = frequencies[1]  # avoid divide-by-zero at DC
    spectrum /= np.sqrt(frequencies)
    return np.fft.irfft(spectrum, n=n_samples)


def _brown_noise(n_samples: int) -> np.ndarray:
    white = np.random.normal(0, 1, n_samples)
    brown = np.cumsum(white)
    return brown


def _normalize_to_int16(signal: np.ndarray) -> np.ndarray:
    signal = signal / np.max(np.abs(signal))
    return (signal * 0.6 * 32767).astype(np.int16)


_GENERATORS = {"white": _white_noise, "pink": _pink_noise, "brown": _brown_noise}


class GenerateAmbientSoundTool(Tool):
    name = "generate_ambient_sound"
    description = "Generate white, pink, or brown noise for focus/sleep, as a playable audio file."
    input_schema = {
        "type": "object",
        "properties": {
            "noise_type": {"type": "string", "enum": ["white", "pink", "brown"]},
            "duration_seconds": {"type": "integer", "description": f"Default 60, max {MAX_DURATION_S}."},
        },
        "required": ["noise_type"],
    }

    def run(self, noise_type: str, duration_seconds: int = 60) -> str:
        if np is None:
            return _NUMPY_MISSING_MSG
        duration_seconds = min(duration_seconds, MAX_DURATION_S)
        n_samples = SAMPLE_RATE * duration_seconds

        signal = _GENERATORS[noise_type](n_samples)
        pcm = _normalize_to_int16(signal)

        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)
        path = output_dir / f"{noise_type}_noise_{duration_seconds}s.wav"

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm.tobytes())

        push_attachment(str(path))
        return f"Generated {duration_seconds}s of {noise_type} noise, saved to {path}."

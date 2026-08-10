"""Always-listening voice interface for a Raspberry Pi with a mic + speaker —
the closest thing to actually talking to Jarvis out loud.

Pipeline: wake word (openWakeWord) -> record utterance -> local STT
(faster-whisper) -> agent -> local TTS (Piper) -> playback. Everything runs
on-device; nothing but the Claude API call itself leaves the Pi.

Requires requirements-voice.txt. Tune SILENCE_* constants for your room/mic.
"""
from __future__ import annotations

import queue
import time

import numpy as np
import sounddevice as sd

from core import attachments
from core.agent import Agent
from core.config import config
from core.memory import Memory
from core.scheduler import ReminderScheduler
from core.store import Store
from core.tts import get_synthesizer
from tools.registry_builder import build_registry

SAMPLE_RATE = 16000
FRAME_SIZE = 1280  # 80ms at 16kHz, openWakeWord's expected chunk size
SILENCE_THRESHOLD = 500  # RMS amplitude below this counts as silence
SILENCE_DURATION_S = 1.2  # stop recording after this much trailing silence
MAX_UTTERANCE_S = 15
SESSION_ID = "voice"


def _rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


class VoiceLoop:
    def __init__(self) -> None:
        from faster_whisper import WhisperModel
        from openwakeword.model import Model as WakeWordModel

        memory = Memory()
        store = Store()
        self._agent = Agent(memory, build_registry(memory, store))
        self._wake_model = WakeWordModel(wakeword_models=[config.wake_word])
        self._stt = WhisperModel("small", device="cpu", compute_type="int8")
        # Uses ElevenLabs if ELEVENLABS_API_KEY is set (expressive, cloud), else
        # local Piper — expects a voice model matching config.voice_language, e.g.
        # ~/.local/share/piper/fr_FR-siwis-medium.onnx — see README for setup.
        self._tts = get_synthesizer(self._piper_model_path() if not config.elevenlabs_api_key else None)
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._scheduler = ReminderScheduler(store, notify=lambda text: self._speak(text, urgent=True))

    def _piper_model_path(self) -> str:
        from pathlib import Path

        candidates = list(Path.home().glob(f".local/share/piper/{config.voice_language}*.onnx"))
        if not candidates:
            raise RuntimeError(
                f"No Piper voice model found for language '{config.voice_language}' in "
                "~/.local/share/piper/. Download one from "
                "https://github.com/rhasspy/piper/blob/master/VOICES.md"
            )
        return str(candidates[0])

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        self._audio_queue.put(indata.copy())

    def _speak(self, text: str, urgent: bool = False) -> None:
        audio = self._tts.synthesize(text, urgent=urgent)
        sd.play(audio, samplerate=self._tts.sample_rate)
        sd.wait()

    def _record_utterance(self, stream: sd.InputStream) -> np.ndarray:
        frames: list[np.ndarray] = []
        silence_start: float | None = None
        start_time = time.time()

        while True:
            chunk = self._audio_queue.get()
            frames.append(chunk)

            if _rms(chunk) < SILENCE_THRESHOLD:
                silence_start = silence_start or time.time()
                if time.time() - silence_start > SILENCE_DURATION_S:
                    break
            else:
                silence_start = None

            if time.time() - start_time > MAX_UTTERANCE_S:
                break

        return np.concatenate(frames).flatten()

    def run(self) -> None:
        print(f"{config.assistant_name} voice loop running. Say '{config.wake_word}' to start.")
        self._scheduler.start()

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SIZE,
            callback=self._audio_callback,
        ) as stream:
            while True:
                chunk = self._audio_queue.get()
                prediction = self._wake_model.predict(chunk.flatten())
                if prediction.get(config.wake_word, 0.0) < 0.5:
                    continue

                print("Wake word detected, listening...")
                # Drain the wake-word chunk backlog so recording starts fresh.
                while not self._audio_queue.empty():
                    self._audio_queue.get_nowait()

                utterance = self._record_utterance(stream)
                segments, _ = self._stt.transcribe(
                    utterance.astype(np.float32) / 32768.0, language=config.voice_language
                )
                text = " ".join(s.text for s in segments).strip()
                if not text:
                    continue

                print(f"you (spoken)> {text}")
                reply = self._agent.respond(SESSION_ID, text)
                print(f"{config.assistant_name}> {reply}")
                self._speak(reply)

                saved_files = attachments.drain()
                if saved_files:
                    print(f"[files saved: {', '.join(saved_files)}]")


def main() -> None:
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
    VoiceLoop().run()


if __name__ == "__main__":
    main()

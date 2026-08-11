"""Always-listening voice interface for a Raspberry Pi with a mic + speaker —
the closest thing to actually talking to Orion out loud.

Pipeline: wake word (openWakeWord) -> record utterance -> local STT
(faster-whisper) -> agent -> local TTS (Piper) -> playback. Everything runs
on-device; nothing but the Claude API call itself leaves the Pi.

Requires requirements-voice.txt. Tune SILENCE_* constants for your room/mic.
"""
from __future__ import annotations

import queue
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from core import attachments
from core.agent import Agent
from core.config import config
from core.health_monitor import HealthMonitor
from core.memory import Memory
from core.scheduler import ReminderScheduler
from core.store import Store
from core.tts import get_synthesizer
from tools.registry_builder import build_registry

_BUNDLED_WAKE_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "wake_word_models"

SAMPLE_RATE = 16000
FRAME_SIZE = 1280  # 80ms at 16kHz, openWakeWord's expected chunk size
SILENCE_THRESHOLD = 500  # fallback RMS amplitude below which counts as silence, until calibrated
# 0.7s matches the trailing-silence window most deployed voice assistants
# use for end-of-utterance detection — close to how quickly a human
# conversation partner treats a pause as "they're done talking." A fixed
# threshold needed more margin to avoid false cutoffs in a noisy room; now
# that SILENCE_THRESHOLD comes from real ambient-noise calibration (below)
# instead of one constant for every room, that margin isn't needed here.
SILENCE_DURATION_S = 0.7
MAX_UTTERANCE_S = 15
SESSION_ID = "voice"

# Ambient noise varies a lot by room/mic, and a fixed SILENCE_THRESHOLD is
# either too twitchy in a noisy room or too slow to notice silence in a
# quiet one. Measure the real ambient level once at startup and set the
# actual threshold from that instead.
CALIBRATION_DURATION_S = 1.5
SILENCE_MARGIN_MULTIPLIER = 2.5  # threshold = ambient RMS * this
MIN_SILENCE_THRESHOLD = 150  # floor, in case the room is closer to silent than any mic's noise floor

# Once the wake word has fired once, keep the conversation open turn after
# turn instead of requiring it again for every exchange (matching the
# Termux interface's behavior). FOLLOWUP_LISTEN_GRACE_S is deliberately more
# generous than SILENCE_DURATION_S: that constant is for detecting when an
# utterance the user has already started *ends*, but deciding whether
# they're going to say anything else at all needs more breathing room than
# that, or the conversation ends before they've had a chance to speak again.
MAX_CONVERSATION_TURNS = 20
FOLLOWUP_LISTEN_GRACE_S = 3.0
STOP_PHRASES = {"stop", "stop listening", "arrête", "arrete", "au revoir", "stop orion", "goodbye"}

# Barge-in: while Orion is talking, a loud-enough sound cuts playback short
# so the user can interrupt instead of having to wait it out. The multiplier
# is much stricter than the ordinary silence threshold on purpose — this is
# a plain RMS check on the same microphone used for everything else, with no
# acoustic echo cancellation, so it needs a real margin to avoid Orion's own
# voice bleeding from the speaker into the mic (worse the closer they are,
# e.g. both built into one Pi case) triggering a false interruption. This
# reduces false positives; it does not eliminate them the way real AEC would.
BARGE_IN_LOUDNESS_MULTIPLIER = 3.0
BARGE_IN_CONSECUTIVE_CHUNKS = 2


def _rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


class VoiceLoop:
    def __init__(self) -> None:
        from faster_whisper import WhisperModel
        from openwakeword.model import Model as WakeWordModel

        memory = Memory()
        store = Store()
        self._agent = Agent(memory, build_registry(memory, store))
        self._wake_model = self._load_wake_model(WakeWordModel)
        self._stt = WhisperModel("small", device="cpu", compute_type="int8")
        # Uses ElevenLabs if ELEVENLABS_API_KEY is set (expressive, cloud), else
        # local Piper — expects a voice model matching config.voice_language, e.g.
        # ~/.local/share/piper/fr_FR-siwis-medium.onnx — see README for setup.
        self._tts = get_synthesizer(self._piper_model_path() if not config.elevenlabs_api_key else None)
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._scheduler = ReminderScheduler(store, notify=lambda text: self._speak(text, urgent=True))
        self._health_monitor = HealthMonitor(store, notify=lambda text: self._speak(text, urgent=True))
        # Overwritten by _calibrate_silence_threshold() once run() starts;
        # this fallback only matters if something (e.g. a reminder) speaks
        # before that's had a chance to run.
        self._silence_threshold = float(SILENCE_THRESHOLD)

    def _load_wake_model(self, wake_word_model_cls):  # noqa: ANN001
        """openWakeWord only ships a handful of pretrained models (alexa,
        hey_mycroft, hey_jarvis, ...) — WAKE_WORD defaults to "hey_orion",
        which isn't one of them. A custom "hey_orion" model trained with
        scripts/wake_word_training/ (see that directory's README) ships at
        wake_word_models/hey_orion.onnx, so the default WAKE_WORD resolves
        to it automatically with no extra setup. Anything else in WAKE_WORD
        (an official bundled name, or a path to your own custom model) is
        passed straight through to openWakeWord as before."""
        model_ref = config.wake_word
        bundled_path = _BUNDLED_WAKE_MODELS_DIR / f"{config.wake_word}.onnx"
        if bundled_path.exists():
            model_ref = str(bundled_path)

        try:
            # Forced explicitly rather than left to openWakeWord's own
            # auto-detection: that only falls back from tflite to onnx when
            # tflite_runtime isn't importable, and tflite_runtime *is*
            # installed on some setups (it's a faster-whisper/piper-tts
            # transitive dependency) — which would otherwise try (and fail)
            # to load our onnx-only custom model as tflite. onnxruntime
            # covers both this and openWakeWord's official bundled models.
            return wake_word_model_cls(wakeword_models=[model_ref], inference_framework="onnx")
        except Exception as exc:
            raise RuntimeError(
                f"Could not load wake word model '{config.wake_word}': {exc}\n"
                "openWakeWord's own pretrained models are alexa, hey_mycroft, hey_jarvis, "
                "timer, and weather. To fix this:\n"
                f"  1. Train a custom '{config.wake_word}' model with scripts/wake_word_training/ "
                "(see that directory's README) and set WAKE_WORD to the resulting model file's "
                "path, or\n"
                "  2. Set WAKE_WORD=hey_jarvis in .env for now to use a working built-in "
                "model while you do that.\n"
                "See README §7 for details."
            ) from exc

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

    def _speak(self, text: str, urgent: bool = False) -> bool:
        """Plays text as speech. Returns True if the user talked loudly
        enough, for long enough, to count as barging in — playback was cut
        short in that case rather than played to completion."""
        raw = self._tts.synthesize(text, urgent=urgent)
        audio = np.frombuffer(raw, dtype=np.int16)
        self._drain_queue()
        sd.play(audio, samplerate=self._tts.sample_rate)

        loud_chunks = 0
        barge_in_level = self._silence_threshold * BARGE_IN_LOUDNESS_MULTIPLIER
        while sd.get_stream().active:
            try:
                chunk = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if _rms(chunk) > barge_in_level:
                loud_chunks += 1
                if loud_chunks >= BARGE_IN_CONSECUTIVE_CHUNKS:
                    sd.stop()
                    return True
            else:
                loud_chunks = 0
        return False

    def _record_utterance(
        self, stream: sd.InputStream, max_initial_silence_s: float | None = None
    ) -> np.ndarray:
        frames: list[np.ndarray] = []
        silence_start: float | None = None
        speech_detected = False
        start_time = time.time()

        while True:
            chunk = self._audio_queue.get()
            frames.append(chunk)

            if _rms(chunk) < self._silence_threshold:
                silence_start = silence_start or time.time()
                limit = SILENCE_DURATION_S if speech_detected else (max_initial_silence_s or SILENCE_DURATION_S)
                if time.time() - silence_start > limit:
                    break
            else:
                speech_detected = True
                silence_start = None

            if time.time() - start_time > MAX_UTTERANCE_S:
                break

        return np.concatenate(frames).flatten()

    def _drain_queue(self) -> None:
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()

    def _calibrate_silence_threshold(self) -> None:
        """Measures the real ambient noise level for a moment so silence
        detection is neither too twitchy (noisy room) nor too slow to
        notice silence (quiet room) with a one-size-fits-all constant."""
        print("Calibrating microphone for ambient noise...")
        self._drain_queue()
        levels = []
        deadline = time.time() + CALIBRATION_DURATION_S
        while time.time() < deadline:
            levels.append(_rms(self._audio_queue.get()))

        ambient = float(np.median(levels)) if levels else float(SILENCE_THRESHOLD)
        self._silence_threshold = max(MIN_SILENCE_THRESHOLD, ambient * SILENCE_MARGIN_MULTIPLIER)
        print(f"Ambient noise level: {ambient:.0f} — silence threshold set to {self._silence_threshold:.0f}")

    def _listen_and_transcribe(self, stream: sd.InputStream, *, is_followup: bool) -> str:
        utterance = self._record_utterance(
            stream, max_initial_silence_s=FOLLOWUP_LISTEN_GRACE_S if is_followup else None
        )
        segments, _ = self._stt.transcribe(
            utterance.astype(np.float32) / 32768.0, language=config.voice_language
        )
        return " ".join(s.text for s in segments).strip()

    def _converse(self, stream: sd.InputStream) -> None:
        """Runs a full back-and-forth once the wake word has fired: keeps
        listening turn after turn — no need to repeat the wake word — until
        the user goes quiet, says a stop phrase, or hits the turn cap."""
        for turn in range(MAX_CONVERSATION_TURNS):
            text = self._listen_and_transcribe(stream, is_followup=turn > 0)
            if not text:
                break  # nothing said — end the conversation, back to wake-word listening

            print(f"you (spoken)> {text}")
            if text.strip().lower() in STOP_PHRASES:
                self._speak("Goodbye.")
                break

            reply = self._agent.respond_streaming(SESSION_ID, text, on_sentence=self._speak)
            print(f"{config.assistant_name}> {reply}")

            saved_files = attachments.drain()
            if saved_files:
                print(f"[files saved: {', '.join(saved_files)}]")

            self._drain_queue()

    def run(self) -> None:
        print(f"{config.assistant_name} voice loop running. Say '{config.wake_word}' to start.")
        self._scheduler.start()
        self._health_monitor.start()

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SIZE,
            callback=self._audio_callback,
        ) as stream:
            self._calibrate_silence_threshold()
            while True:
                chunk = self._audio_queue.get()
                prediction = self._wake_model.predict(chunk.flatten())
                if prediction.get(config.wake_word, 0.0) < 0.5:
                    continue

                print("Wake word detected, listening...")
                self._drain_queue()  # drop the wake-word backlog so recording starts fresh
                self._converse(stream)


def main() -> None:
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
    VoiceLoop().run()


if __name__ == "__main__":
    main()

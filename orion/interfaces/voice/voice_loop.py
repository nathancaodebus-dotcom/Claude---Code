"""Always-listening voice interface for a Raspberry Pi with a mic + speaker —
the closest thing to actually talking to Orion out loud.

Pipeline: wake word (openWakeWord) -> record utterance -> local STT
(faster-whisper) -> agent -> local TTS (Piper) -> playback. Everything runs
on-device; nothing but the Claude API call itself leaves the Pi.

Requires requirements-voice.txt. Tune SILENCE_* constants for your room/mic.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from core import attachments
from core.agent import Agent
from core.config import config
from core.health_monitor import HealthMonitor
from core.logging_setup import configure_logging
from core.memory import Memory
from core.outputs_cleanup import purge_old_outputs
from core.scheduler import ReminderScheduler
from core.stt import join_confident_segments
from core.store import Store
from core.tts import find_local_piper_model, get_synthesizer
from tools.registry_builder import build_registry

logger = logging.getLogger("orion.voice_loop")

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
# Termux interface's behavior). INITIAL_SILENCE_GRACE_S is deliberately more
# generous than SILENCE_DURATION_S: that constant is for detecting when an
# utterance the user has already started *ends*, but deciding whether
# they're going to say anything at all needs more breathing room than that,
# or the conversation ends before they've had a chance to speak.
#
# This used to only apply to follow-up turns (turn > 0), on the theory that
# right after the wake word fires the user is already mid-sentence and
# needs no grace at all — in practice that's backwards: the moment right
# after "hey orion" (println, wake model inference, the user's own reaction
# time) is exactly when the *most* grace is needed, and giving it only the
# 0.7s trailing-silence cutoff meant a recording that started before the
# user had even opened their mouth, got fed to faster-whisper, and either
# came back empty or (see core/stt.py) as a Whisper hallucination — visibly
# reproduced live: "Ambient noise level: 118" and "Processing audio with
# duration 00:00.800" on turn 1, immediately back to wake-word listening
# with nothing captured. Same grace period on every turn now, not just
# follow-ups.
MAX_CONVERSATION_TURNS = 20
INITIAL_SILENCE_GRACE_S = 3.0
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


class _StreamingSpeech:
    """Lets a reply's text generation, TTS synthesis, and audio playback
    all overlap instead of running strictly one sentence at a time —
    without this, on_sentence(text) synthesized *and played* each
    sentence before returning, which paused Claude's own streaming
    generation for that whole duration (nothing was being read off the
    response stream while blocked) on top of the synthesis+playback time
    itself. Every sentence boundary was dead air at least as long as that
    sentence's synthesis took — worse with a network TTS backend like
    Edge TTS — which is what choppy, stop-start ("saccadé") playback
    actually was, not an audio quality problem.

    Two background threads (synthesis, playback) each keep working ahead
    while the other stages proceed: on_sentence() just queues text and
    returns immediately, so generation is never blocked; synthesis for
    sentence N+1 starts as soon as its text arrives, usually while
    sentence N is still playing; playback starts on each sentence the
    moment its audio is ready rather than waiting for the whole reply."""

    def __init__(self, voice_loop: "VoiceLoop") -> None:
        self._voice_loop = voice_loop
        self._sentences: queue.Queue[str | None] = queue.Queue()
        self._audio: queue.Queue[np.ndarray | None] = queue.Queue()
        self._barged_in = False
        self._synth_thread = threading.Thread(target=self._synthesize_loop, daemon=True)
        self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._synth_thread.start()
        self._playback_thread.start()

    def _synthesize_loop(self) -> None:
        while True:
            text = self._sentences.get()
            if text is None:
                self._audio.put(None)  # tell the playback loop there's nothing more coming
                return
            if self._barged_in:
                # respond_streaming doesn't know a barge-in happened and
                # keeps calling on_sentence for the rest of its reply
                # regardless — keep draining those (so on_sentence never
                # backs up) but stop paying for synthesis on sentences that
                # will just be discarded unplayed, so finish() isn't stuck
                # waiting on pointless work before it can hand control back
                # to listening for what the user actually barged in to say.
                continue
            try:
                audio = self._voice_loop._synthesize_audio(text)
            except Exception:
                # One sentence's TTS backend hiccup (e.g. a network blip on
                # Edge TTS) must not silently deadlock finish() below,
                # which waits for this thread to eventually send the None
                # sentinel — skip the sentence and keep going instead.
                logger.exception("TTS synthesis failed for a queued sentence; skipping it.")
                continue
            if audio is not None:
                self._audio.put(audio)

    def _playback_loop(self) -> None:
        while True:
            audio = self._audio.get()
            if audio is None:
                return
            if self._barged_in:
                continue  # drain the rest of the reply without playing it
            try:
                if self._voice_loop._play_audio(audio):
                    self._barged_in = True
            except Exception:
                logger.exception("Audio playback failed for a queued sentence; skipping it.")

    def on_sentence(self, text: str) -> None:
        self._sentences.put(text)

    def finish(self) -> bool:
        """Call once the reply's full text is done generating. Blocks
        until every queued sentence has played (or a barge-in cuts the
        rest short), then returns whether that happened."""
        self._sentences.put(None)
        self._synth_thread.join()
        self._playback_thread.join()
        return self._barged_in


class VoiceLoop:
    def __init__(self) -> None:
        from faster_whisper import WhisperModel
        from openwakeword.model import Model as WakeWordModel

        memory = Memory()
        store = Store()
        self._agent = Agent(memory, build_registry(memory, store))
        self._wake_model = self._load_wake_model(WakeWordModel)
        self._stt = WhisperModel(config.whisper_model_size, device="cpu", compute_type="int8")
        # ElevenLabs if ELEVENLABS_API_KEY is set (expressive, cloud) > local
        # Piper if a voice model matching config.voice_language is found (e.g.
        # ~/.local/share/piper/fr_FR-siwis-medium.onnx — see README §7 for
        # setup) > Edge TTS, a free cloud fallback needing no local model file
        # at all, so a fresh install still has a working voice out of the box.
        self._tts = get_synthesizer(find_local_piper_model())
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

        # openWakeWord needs its frozen feature-extraction (melspectrogram +
        # embedding) and VAD models on disk before it can load *any*
        # wakeword model, custom or official, and doesn't fetch them on its
        # own — nothing in this project ever called this before, so it's
        # only ever worked in environments where something else happened to
        # trigger the download. download_models() no-ops per file that
        # already exists, so this is cheap on every later startup.
        from openwakeword.utils import download_models

        download_models(model_names=[config.wake_word])

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

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        self._audio_queue.put(indata.copy())

    def _speak(self, text: str, urgent: bool = False) -> bool:
        """Synthesizes and plays one utterance, blocking until done (or
        until barged in). Used as-is for output with nothing to pipeline
        against — reminders, health alerts, the stop-phrase goodbye; a
        full conversation turn's multiple sentences go through
        _StreamingSpeech instead (see _converse), which uses the same two
        pieces below without blocking generation/synthesis on playback."""
        audio = self._synthesize_audio(text, urgent=urgent)
        if audio is None:
            return False
        return self._play_audio(audio)

    def _synthesize_audio(self, text: str, urgent: bool = False) -> np.ndarray | None:
        raw = self._tts.synthesize(text, urgent=urgent)
        if not raw:
            # e.g. a fragment that was pure markdown/list-marker punctuation
            # ('1.') and stripped down to nothing — nothing to play.
            return None
        return np.frombuffer(raw, dtype=np.int16)

    def _play_audio(self, audio: np.ndarray) -> bool:
        """Blocks until playback finishes. Returns True if the user talked
        loudly enough, for long enough, to count as barging in — playback
        was cut short in that case rather than played to completion. Only
        actually checks for that if VOICE_BARGE_IN_ENABLED is set (see
        core/config.py) — off by default, since without real acoustic echo
        cancellation this is a plain RMS check on the same mic Orion's own
        voice plays out of, and on a laptop's built-in speakers+mic (inches
        apart) that reliably means Orion hears itself and cuts itself off
        mid-reply."""
        self._drain_queue()
        sd.play(audio, samplerate=self._tts.sample_rate)

        if not config.voice_barge_in_enabled:
            sd.wait()
            return False

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

    def _listen_and_transcribe(self, stream: sd.InputStream) -> str:
        utterance = self._record_utterance(stream, max_initial_silence_s=INITIAL_SILENCE_GRACE_S)
        segments, _ = self._stt.transcribe(
            utterance.astype(np.float32) / 32768.0, language=config.voice_language
        )
        return join_confident_segments(segments)

    def _converse(self, stream: sd.InputStream) -> None:
        """Runs a full back-and-forth once the wake word has fired: keeps
        listening turn after turn — no need to repeat the wake word — until
        the user goes quiet, says a stop phrase, or hits the turn cap."""
        for turn in range(MAX_CONVERSATION_TURNS):
            text = self._listen_and_transcribe(stream)
            if not text:
                if turn == 0:
                    # The wake word itself fired (so something loud enough
                    # triggered it), but nothing usable followed — the mic
                    # didn't catch real speech in time, or Whisper wasn't
                    # confident about what it heard (core/stt.py). Worth
                    # saying so: silently dropping back to wake-word
                    # listening here reads as Orion ignoring the user, not
                    # as "it didn't catch that." Turn > 0 with nothing said
                    # is the normal, expected way a conversation ends
                    # (the user just stopped talking) and doesn't get this.
                    self._speak("Je n'ai pas bien entendu, tu peux réessayer.")
                break  # nothing said — end the conversation, back to wake-word listening

            print(f"you (spoken)> {text}")
            if text.strip().lower() in STOP_PHRASES:
                self._speak("Goodbye.")
                break

            # _StreamingSpeech overlaps this reply's generation, TTS
            # synthesis, and playback instead of running them strictly one
            # sentence at a time (see its docstring) — on_sentence here
            # only queues text, so respond_streaming's own generation is
            # never blocked waiting on synthesis or playback.
            speech = _StreamingSpeech(self)
            try:
                reply = self._agent.respond_streaming(SESSION_ID, text, on_sentence=speech.on_sentence)
            finally:
                # Always sends the sentinel that lets the two background
                # threads finish and exit, even if respond_streaming raised
                # partway through — otherwise a failed turn leaks both
                # threads (blocked forever on their queues) for the rest of
                # this long-running process's life instead of just ending
                # cleanly, same as every other turn.
                speech.finish()
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
                try:
                    self._converse(stream)
                except Exception:
                    # This is an always-on service (README §8, typically a
                    # systemd unit) — one bad turn (a TTS backend hiccup, a
                    # transient STT failure, anything unexpected) must not
                    # take down the whole process and silently stop
                    # listening for the wake word until someone notices and
                    # restarts it. Same reasoning as ReminderScheduler/
                    # HealthMonitor's poll loops: log it, keep running.
                    logger.exception("Conversation turn failed; listening for the wake word again.")


def main() -> None:
    configure_logging()
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
    purge_old_outputs(Path("outputs"), config.outputs_retention_days)
    VoiceLoop().run()


if __name__ == "__main__":
    main()

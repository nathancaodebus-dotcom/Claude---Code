"""Talk to Orion directly from an Android phone via Termux — no Telegram,
no Raspberry Pi, no heavy ML models installed on the phone. Speech
recognition and speech synthesis both go through Android's own built-in
engines via Termux:API (`termux-speech-to-text` / `termux-tts-speak`), so
the only Python dependencies this needs on-device are Orion's lightweight
core ones (anthropic, httpx, ...) — nothing like faster-whisper, Piper, or
openWakeWord, which are unlikely to build cleanly in Termux's environment.

Honest limitation: this is tap-to-talk, not hands-free wake-word. Android
doesn't let a background script listen continuously for a wake word without
a dedicated foreground-service app (which this isn't) — so a shortcut tap
(or running this script) starts one *conversation*, which then keeps
listening turn after turn on its own until you go quiet or say a stop
phrase, without needing to tap again for each exchange.

Setup (see README §11 for the full walkthrough):
    1. Install Termux and Termux:API from F-Droid (not the Play Store builds).
    2. pkg install python
    3. pip install -r requirements.txt   (some packages may not have prebuilt
       wheels for Termux and fail to install — that's fine, thanks to the
       same plugin architecture used everywhere else here, any tool whose
       dependency didn't install just stays disabled)
    4. cp .env.example .env, fill in ANTHROPIC_API_KEY
    5. python -m interfaces.termux.orion_termux
    6. Optional: copy orion.sh into ~/.shortcuts/ for a Termux:Widget
       home-screen button that starts a conversation with one tap.
"""
from __future__ import annotations

import subprocess

from core.agent import Agent
from core.config import config
from core.memory import Memory
from core.store import Store
from tools.registry_builder import build_registry

SESSION_ID = "termux"
MAX_TURNS_PER_SESSION = 20
STOP_PHRASES = {"stop", "stop listening", "arrête", "arrete", "au revoir", "stop orion", "goodbye"}
LISTEN_TIMEOUT_S = 30


def _listen() -> str:
    """Blocks on Android's speech recognition dialog (via Termux:API) until
    the user speaks or it times out; returns the transcript, or '' on timeout
    /no speech detected."""
    try:
        result = subprocess.run(
            ["termux-speech-to-text"], capture_output=True, text=True, timeout=LISTEN_TIMEOUT_S
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            "termux-speech-to-text not found. Install the Termux:API app (F-Droid) and "
            "run `pkg install termux-api` in Termux first."
        ) from exc
    except subprocess.TimeoutExpired:
        return ""
    return result.stdout.strip()


def _speak(text: str) -> None:
    subprocess.run(["termux-tts-speak", text], timeout=60)


def _notify(text: str) -> None:
    # Best-effort — a missing/failing notification shouldn't stop the conversation.
    subprocess.run(
        ["termux-notification", "--title", config.assistant_name, "--content", text[:200]],
        capture_output=True,
        timeout=10,
    )


def run_conversation(agent: Agent) -> None:
    subprocess.run(["termux-wake-lock"], capture_output=True, timeout=10)
    try:
        for _ in range(MAX_TURNS_PER_SESSION):
            _notify("Listening…")
            transcript = _listen()

            if not transcript:
                _notify("Didn't catch anything — ending the conversation.")
                break

            if transcript.strip().lower() in STOP_PHRASES:
                _speak("Goodbye.")
                break

            _notify(f"You: {transcript}")
            reply = agent.respond(SESSION_ID, transcript)
            _notify(reply[:200])
            _speak(reply)
    finally:
        subprocess.run(["termux-wake-unlock"], capture_output=True, timeout=10)


def main() -> None:
    if not config.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")

    memory = Memory()
    store = Store()
    agent = Agent(memory, build_registry(memory, store))
    run_conversation(agent)


if __name__ == "__main__":
    main()

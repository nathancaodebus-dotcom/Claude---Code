# Jarvis

A personal AI assistant you can talk to about anything, at any time — it
reads your email, manages your calendar, controls your smart home, and
remembers things about you across conversations. One agent core, three
interfaces (terminal, Telegram/Android, always-listening voice on a
Raspberry Pi).

## How it's built

```
jarvis/
  core/
    agent.py        # the Claude tool-use loop every interface shares
    memory.py       # SQLite: conversation history + long-term facts
    store.py        # SQLite: to-dos, notes, shopping list, reminders/timers
    scheduler.py     # background poller that fires due reminders/timers
    attachments.py   # lets a tool hand a generated file back to the interface
    config.py       # settings, loaded from .env
  tools/           # one file per capability group — see full list below
  interfaces/
    cli.py             # terminal chat, for local testing
    telegram_bot.py    # Telegram bot — this is your Android access point
    voice/voice_loop.py # wake word + local STT/TTS, for a Raspberry Pi
  systemd/         # unit files to run interfaces as background services on the Pi
```

Adding a new capability means writing one `Tool` subclass in `tools/` and
registering it in `tools/registry_builder.py` — nothing else changes.

## What Jarvis can do out of the box

33 tools, registered in `tools/registry_builder.py`:

| Category | Tools |
|---|---|
| Memory | remember/recall durable facts about you |
| Email & calendar *(needs Google setup, §2)* | search/read Gmail, list/create calendar events |
| Smart home *(needs Home Assistant, §3)* | list devices, control any light/switch/climate entity |
| Productivity | to-dos, notes, shopping list, reminders & timers (with proactive Telegram delivery) |
| Live info | weather, sunrise/sunset, Wikipedia summaries, currency conversion, stock prices, news headlines |
| Open web | web search, fetch & read a webpage, shorten a URL, public IP lookup |
| Utilities | calculator, unit conversion, password generator, QR code generator |
| Self-monitoring | CPU/temperature/memory/disk/uptime of the machine it runs on |
| Just for fun | coin flip, dice roll, magic 8-ball, random quote, joke |

Everything except Gmail/Calendar/Home Assistant works with zero extra setup
— just the Anthropic API key — since the live-info and web tools use free,
keyless public APIs (Open-Meteo, Wikipedia, frankfurter.app, stooq,
DuckDuckGo, Google News RSS).

## 1. Setup

```bash
cd jarvis
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- `ANTHROPIC_API_KEY` — required. Get one at https://console.anthropic.com.
- Everything else is optional — each integration turns itself on only when
  its config is present, so you can start with just the API key.

Test the core loop first:

```bash
python -m interfaces.cli
```

## 2. Gmail + Google Calendar

1. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project, enable the **Gmail API** and **Google Calendar API**.
2. Create an **OAuth client ID** of type "Desktop app", download the JSON,
   save it as `credentials.json` in this folder (or point
   `GOOGLE_CREDENTIALS_PATH` at it).
3. Run `python -m interfaces.cli` and ask Jarvis to check your email — it
   will open a browser to authorize on first use, then cache a token so it
   never asks again.

## 3. Home Assistant (domotique)

Home Assistant is the easiest self-hosted hub for controlling lights,
switches, thermostats, etc. regardless of brand — it can run on the same
Raspberry Pi as Jarvis.

1. Install Home Assistant ([installation guide](https://www.home-assistant.io/installation/raspberrypi/)),
   pair your devices with it as you normally would.
2. In Home Assistant, go to your profile → **Long-Lived Access Tokens** →
   create one.
3. Set `HOME_ASSISTANT_URL` (e.g. `http://homeassistant.local:8123`) and
   `HOME_ASSISTANT_TOKEN` in `.env`.

## 4. Android access via Telegram

No app to build — Telegram already has a great Android client with voice
messages and push notifications.

1. Message [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`,
   follow the prompts, copy the token into `TELEGRAM_BOT_TOKEN`.
2. Message [@userinfobot](https://t.me/userinfobot) to get your numeric
   user id, put it in `TELEGRAM_ALLOWED_USER_ID` (this locks the bot to
   only you).
3. Run it:
   ```bash
   python -m interfaces.telegram_bot
   ```
4. Open your bot in Telegram on your phone and start chatting — text or
   voice messages both work (voice needs `requirements-voice.txt`
   installed for local transcription). Reminders/timers you set are
   pushed to you automatically when they come due, and anything Jarvis
   generates as a file (e.g. a QR code) is sent back as a photo/document.

## 5. Always-listening voice on a Raspberry Pi

For the closest experience to actually talking to Jarvis out loud:

```bash
pip install -r requirements-voice.txt
```

Download a [Piper](https://github.com/rhasspy/piper/blob/master/VOICES.md)
voice model for your language into `~/.local/share/piper/` (e.g.
`fr_FR-siwis-medium.onnx` for French).

```bash
python -m interfaces.voice.voice_loop
```

Say the wake word (`WAKE_WORD` in `.env`, default `hey_jarvis`), then
speak your request; Jarvis answers out loud.

## 6. Running as background services on the Pi

```bash
sudo cp systemd/jarvis-telegram.service systemd/jarvis-voice.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-telegram jarvis-voice
```

Edit the `User=`, `WorkingDirectory=` and venv path in the unit files first
if your setup differs from `/home/pi/jarvis`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Privacy notes

- Only your Anthropic API calls leave the device by default; STT/TTS for
  the voice interface run entirely locally (Whisper + Piper).
- The Telegram bot only responds to `TELEGRAM_ALLOWED_USER_ID` — anyone
  else's messages are silently ignored.
- All memory (conversation history, remembered facts) lives in a local
  SQLite file (`JARVIS_DB_PATH`) — nothing is synced anywhere.

# Jarvis

A personal AI assistant you can talk to about anything, at any time — it
reads your email, manages your calendar, controls your smart home, creates
and edits PowerPoint/Word/Excel files on request, controls Spotify and casts
video to your TV, and remembers things about you across conversations. One
agent core, three interfaces (terminal, Telegram/Android, always-listening
voice on a Raspberry Pi) — anything you dictate out loud goes through the
same tool-using loop as typed text.

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

Up to 64 tools, registered in `tools/registry_builder.py` depending on what's configured:

| Category | Tools |
|---|---|
| Memory | remember/recall durable facts about you |
| Email & calendar *(needs Google setup, §2)* | search/read Gmail, list/create calendar events |
| Smart home *(needs Home Assistant, §3)* | list devices, control any light/switch/climate entity |
| Productivity | to-dos, notes, shopping list, reminders & timers (with proactive Telegram delivery) |
| **Documents** | create/edit **PowerPoint** (add/edit/delete slides), **Word** (append paragraphs/headings), **Excel** (add rows) — dictate 'create me a presentation about X', then 'add a slide about Y', and Jarvis edits the same file |
| **Music** *(needs Spotify setup, §4)* | search, play, pause, resume, skip, volume, list Spotify Connect devices |
| **Video / casting** *(needs Chromecast setup, §5)* | discover Chromecasts, search & play YouTube videos, launch Netflix/Disney+/Spotify/YouTube Music on the TV, pause/resume/stop/volume — see the important caveat in §5 |
| Live info | weather, sunrise/sunset, Wikipedia summaries, currency conversion, stock prices, news headlines |
| Open web | web search, fetch & read a webpage, shorten a URL, public IP lookup |
| Utilities | calculator, unit conversion, password generator, QR code generator |
| Self-monitoring | CPU/temperature/memory/disk/uptime of the machine it runs on |
| Just for fun | coin flip, dice roll, magic 8-ball, random quote, joke |

Everything except Gmail/Calendar/Home Assistant/Spotify/YouTube/Chromecast
works with zero extra setup — just the Anthropic API key — since the
live-info, web, and document tools use free, keyless public APIs or local
libraries (Open-Meteo, Wikipedia, frankfurter.app, stooq, DuckDuckGo,
Google News RSS, python-pptx/docx/openpyxl).

Because every interface (CLI, Telegram voice messages, the Raspberry Pi
voice loop) funnels through the same tool-using agent, anything dictated
out loud works exactly like typed text — 'crée-moi un PowerPoint sur le
projet X' triggers `create_presentation` whether you type it or say it.

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

## 4. Spotify (music control)

1. Create an app at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard),
   add `http://localhost:8888/callback` (or your own `SPOTIFY_REDIRECT_URI`) as
   a Redirect URI.
2. Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env`.
3. Run `python -m interfaces.cli` and ask Jarvis to play something — first
   use opens a browser to authorize, then caches a token.

**Requires Spotify Premium** and a device with Spotify Connect active (the
Spotify app open on your phone, a smart speaker, or
[spotifyd](https://github.com/Spotifyd/spotifyd) running on the Pi itself) —
the Web API only *controls* playback on an existing device, it doesn't
stream audio by itself.

## 5. YouTube + casting to a Chromecast/Google TV (and launching Netflix, Disney+, YouTube Music)

**Read this before expecting more than it can do.** Netflix and Disney+
publish no public API for search or playback — nobody outside Netflix/Disney
can build a real "find and play this movie" integration for them, and any
tool claiming otherwise is scraping or reverse-engineering their apps in a
way that's fragile and against their terms. What Jarvis *can* do
legitimately, using Google's standard Cast protocol (the same thing your
phone's "Cast" button uses):

- **YouTube**: real search + "play this exact video" — Google documents an
  official Cast controller for it.
- **Netflix / Disney+ / YouTube Music**: launch the app on your TV, same as
  casting from your phone. You still pick the title yourself once it's open.
- **Spotify**: prefer the dedicated Spotify tools in §4 for actual playback
  control; casting can also just open the Spotify app on the TV.

Setup:

1. Get a free `YOUTUBE_API_KEY` from
   [Google Cloud Console](https://console.cloud.google.com/) (enable
   "YouTube Data API v3" — no OAuth needed, just an API key).
2. Set `CHROMECAST_NAME` in `.env` to your device's name as shown in the
   Google Home app.
3. `pip install -r requirements.txt` already includes `PyChromecast`.

If launching Netflix/Disney+/YouTube Music stops working, their Chromecast
app ids may have changed — override them via `CHROMECAST_APP_IDS` in `.env`
(JSON, e.g. `{"netflix": "XXXXXXXX"}`); ask Jarvis to `list_chromecasts`
first to confirm it can see your TV at all.

## 6. Android access via Telegram

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

## 7. Always-listening voice on a Raspberry Pi

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

## 8. Running as background services on the Pi

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

# Orion

**O.R.I.O.N. — Omniscient Reconnaissance & Intelligence Network.**

A personal AI assistant you can talk to about anything, at any time — it
reads your email, manages your calendar, controls your smart home, creates
and edits PowerPoint/Word/Excel files on request, controls Spotify and casts
video to your TV, and remembers things about you across conversations. One
agent core, four interfaces (terminal, Telegram voice conversations on
Android, a Termux tap-to-talk shortcut also on Android, always-listening
voice on a Raspberry Pi) — anything you dictate out loud goes through the
same tool-using loop as typed text. **Phone and Pi are both fully
operational voice interfaces**, not one primary and one afterthought — see
§6/§11 for the phone and §7 for the Pi.

## How it's built

```
orion/
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

## What Orion can do out of the box

Around 90-130 tools depending on configuration, registered in
`tools/registry_builder.py`:

| Category | Tools |
|---|---|
| Memory | remember/recall durable facts, preferences, and corrections; **semantic memory** (search_memory/index_memory, §10) for recalling something by meaning, not exact wording |
| Email & calendar *(needs Google setup, §2)* | search/read Gmail, draft emails, **archive/mark-read/count unread** (triage, never auto-sends), list/create Google Calendar events, search/add contacts |
| Other calendars *(§9)* | list/create events on **any CalDAV calendar** — Outlook, iCloud, Nextcloud |
| Task managers | built-in to-dos, or **Todoist** (§9) if that's where you already live |
| Notes | built-in notes, or straight into your **Obsidian vault** (§9) as markdown |
| Smart home *(needs Home Assistant, §3)* | list devices, control any light/switch/climate entity |
| Productivity | to-dos, notes, shopping list, reminders & timers, project/milestone tracking, **meeting briefing dossiers** (prep on a person/company before a meeting) |
| **Documents** | create/edit PowerPoint/Word/Excel (rows, formulas, charts) by voice or text; **read** existing PDF/Word/any text or code file; **interactive charts** (Plotly) |
| **Music** *(needs Spotify setup, §4)* | search, play, pause, resume, skip, volume, create/fill playlists, list Spotify Connect devices |
| **Video / casting** *(needs Chromecast setup, §5)* | discover Chromecasts, search & play YouTube videos, launch Netflix/Disney+/Spotify/YouTube Music on the TV — see the caveat in §5 |
| Live info | weather (+ historical comparison), sunrise/sunset, Wikipedia, dictionary, currency, stocks, crypto, news, RSS, Reddit, GitHub watching, upcoming movies |
| Open web | web search, fetch & read a webpage, shorten a URL, public IP, service uptime checks |
| Utilities | calculator, unit conversion, password generator, QR codes, ambient noise generator, **flashcard/quiz generator** (real Anki .apkg files) |
| **Dev tools** *(§10)* | **natural-language SQL queries** (read-only by default), **code security audit** (bandit + OSV vulnerability lookup), **named build/deploy commands**, **sub-agent delegation** (researcher/coder/writer/critic) |
| System / files | CPU/temp/memory/disk/uptime, **top processes + priority control**, **disk health (SMART)**, find large/duplicate files, local backups, network speed test, failed-command log |
| Automation | run short Python scripts on demand (Docker-isolated if available, else subprocess) — off by default |
| Safety | emergency alert with location, **kill switch** (wipe local data on a confirmation phrase), **credential leak checking** (HIBP) |
| Vision | **analyze/critique a supplied image** (design mockups, screenshots, photos — no camera needed, works on any image file) |
| Just for fun | coin flip, dice, 8-ball, quotes, jokes, song lyrics, YouTube transcripts/summaries |
| **Briefings** | `morning_briefing`, `evening_debrief`, `prepare_meeting_briefing` |

Everything except Gmail/Calendar/Home Assistant/Spotify/YouTube/Chromecast/
CalDAV/Todoist/TMDb works with zero extra setup — just the Anthropic API
key — since most of this uses free, keyless public APIs or local libraries
(Open-Meteo, Wikipedia, frankfurter.app, stooq, CoinGecko, dictionaryapi.dev,
DuckDuckGo, Google News RSS, Reddit's public JSON API, GitHub's public API,
lyrics.ovh, youtube-transcript-api, python-pptx/docx/openpyxl, pypdf).

Because every interface (CLI, Telegram voice messages, the Raspberry Pi
voice loop) funnels through the same tool-using agent, anything dictated
out loud works exactly like typed text — 'crée-moi un PowerPoint sur le
projet X' triggers `create_presentation` whether you type it or say it.

## How Orion learns

Memory here works on two tracks, both automatic — neither requires the user
to say "remember this":

- **Facts, preferences, and corrections** (`core/memory.py`, the `facts`
  table): the system prompt instructs the model to call `remember_fact`
  whenever it notices something durable worth keeping — not just stated
  facts, but preferences it infers and corrections the user makes ("no,
  I meant the other calendar" becomes a stored rule, not a one-off fix).
  These are global, visible to every interface and session.
- **Conversation assimilation** (`core/consolidation.py`): `Memory.history()`
  only ever sends the most recent ~40 messages to the model, so a long
  running conversation would normally just lose everything older than that.
  Instead, once a session passes 60 messages, the oldest overflow gets
  folded into a running per-session summary via one extra Claude call —
  merged with whatever was summarized before — so the gist of a long
  relationship survives even after the raw messages scroll out of context.
  This runs automatically at the end of every `Agent.respond()` call.

Both are visible in `recall_facts` and, for a given session, in the
"Summary of earlier conversation" block Orion sees in its own system
prompt — nothing here is hidden state.

## 1. Setup

```bash
cd orion
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
3. Run `python -m interfaces.cli` and ask Orion to check your email — it
   will open a browser to authorize on first use, then cache a token so it
   never asks again.

## 3. Home Assistant (domotique)

Home Assistant is the easiest self-hosted hub for controlling lights,
switches, thermostats, etc. regardless of brand — it can run on the same
Raspberry Pi as Orion.

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
3. Run `python -m interfaces.cli` and ask Orion to play something — first
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
way that's fragile and against their terms. What Orion *can* do
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
(JSON, e.g. `{"netflix": "XXXXXXXX"}`); ask Orion to `list_chromecasts`
first to confirm it can see your TV at all.

## 6. Android access via Telegram — a real voice conversation, not just chat

No app to build — Telegram already has a great Android client with voice
messages and push notifications. Send Orion a voice message and it **speaks
back** with a voice message of its own, not just text — this is the
"talk to Orion from your phone" path, and it's fully operational once set up.

1. Message [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`,
   follow the prompts, copy the token into `TELEGRAM_BOT_TOKEN`.
2. Message [@userinfobot](https://t.me/userinfobot) to get your numeric
   user id, put it in `TELEGRAM_ALLOWED_USER_ID` (this locks the bot to
   only you).
3. For spoken replies (not just transcription of what you said), set up
   text-to-speech: either `ELEVENLABS_API_KEY` (cloud, works anywhere this
   bot runs, no local model needed), or a local Piper model as described
   in §7 if this bot happens to run on the same machine as the voice loop.
   Without either, voice messages still work — you just get a text reply
   instead of a spoken one.
4. Install [ffmpeg](https://ffmpeg.org/) (`apt install ffmpeg` / `brew
   install ffmpeg`) — needed to encode replies into the Opus format
   Telegram requires for voice notes. Without it, replies fall back to text.
5. Run it:
   ```bash
   python -m interfaces.telegram_bot
   ```
6. Open your bot in Telegram on your phone. Text in gets text back; a voice
   message in gets transcribed *and* answered with a spoken voice message
   back (plus the text, for reference) — a real back-and-forth conversation,
   asynchronous like any voice note, from anywhere with signal, not just at
   home. Reminders/timers are pushed to you automatically when due (spoken
   too, if TTS is configured), and anything Orion generates as a file
   (e.g. a QR code) is sent back as a photo/document.

This runs wherever you start the process — the Raspberry Pi, a home server,
or even the same laptop as the CLI. Point it at the same `ORION_DB_PATH` as
your Pi's voice loop and they share memory/facts/to-dos; point it at a
different one and they're independent.

## 7. Always-listening voice on a Raspberry Pi

For the closest experience to actually talking to Orion out loud:

```bash
pip install -r requirements-voice.txt
```

Download a [Piper](https://github.com/rhasspy/piper/blob/master/VOICES.md)
voice model for your language into `~/.local/share/piper/` (e.g.
`fr_FR-siwis-medium.onnx` for French).

```bash
python -m interfaces.voice.voice_loop
```

Say the wake word (`WAKE_WORD` in `.env`), then speak your request; Orion
answers out loud.

**The `hey_orion` default won't actually trigger yet.** openWakeWord only
ships a handful of pretrained models — alexa, hey_mycroft, hey_jarvis,
timer, weather — and "hey_orion" isn't one of them, so there's no ready-made
model for it. `VoiceLoop` fails fast at startup with instructions rather
than silently never detecting anything. Until a custom model is trained
(openWakeWord's training notebook, ~30-60 min) and `WAKE_WORD` is pointed
at it — or a different wake-word engine that supports arbitrary phrases is
wired in instead — set `WAKE_WORD=hey_jarvis` to use the working built-in
model in the meantime.

Once the wake word has fired, the conversation stays open — keep talking
turn after turn without repeating it, until you go quiet, say "stop" (or
"arrête"), or hit the 20-turn cap. Replies are also streamed sentence by
sentence: Orion starts speaking the first sentence as soon as it's ready
instead of waiting for the whole answer, and the (fairly large) set of tool
definitions sent to Claude on every turn is prompt-cached so it isn't
reprocessed from scratch each time — both cut down the pause between asking
and hearing a reply.

On first start (and each time you launch it), it spends about a second and
a half measuring the room's actual background noise and sets its
silence-detection threshold from that, rather than a fixed value that's
wrong for most rooms/mics. You can also talk over Orion while it's
speaking to cut it off and start your next turn immediately, instead of
having to wait for it to finish — though since this is a plain volume
check on the same mic (no real echo cancellation), a speaker and mic
crammed close together may occasionally misfire; move them apart a bit if
that happens.

## 8. Running as background services on the Pi

```bash
sudo cp systemd/orion-telegram.service systemd/orion-voice.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now orion-telegram orion-voice
```

Edit the `User=`, `WorkingDirectory=` and venv path in the unit files first
if your setup differs from `/home/pi/orion`.

## 9. Optional extras (calendars, tasks, notes, movies, backups, safety, automation)

These all follow the same pattern as everything else — set the relevant
`.env` variables and the tool turns itself on, no code changes needed.

- **CalDAV** (Outlook / iCloud / Nextcloud calendars): `CALDAV_URL`,
  `CALDAV_USERNAME`, `CALDAV_PASSWORD`. For iCloud, use
  `https://caldav.icloud.com` with an
  [app-specific password](https://appleid.apple.com).
- **Todoist**: `TODOIST_API_TOKEN` from Todoist Settings → Integrations →
  Developer. Independent from Orion's own built-in to-do list — use
  whichever (or both).
- **Obsidian**: `OBSIDIAN_VAULT_PATH` pointing at your vault folder (or any
  folder — it's just markdown files, Obsidian reads the filesystem).
- **GitHub release/commit watcher**: works with no token (60 requests/hour);
  set `GITHUB_WATCH_TOKEN` for 5000/hour.
- **TMDb** (upcoming movies): free `TMDB_API_KEY` from
  [themoviedb.org](https://www.themoviedb.org/settings/api).
- **Local backups**: `BACKUP_SOURCE_PATH` / `BACKUP_DEST_PATH` for a default
  pair, or pass paths explicitly each time. Plain recursive copy — point
  `BACKUP_DEST_PATH` at an rclone/Syncthing mount for anything fancier.
- **Emergency alert**: `EMERGENCY_CONTACT_CHAT_IDS` (comma-separated
  Telegram chat ids from @userinfobot) — reuses `TELEGRAM_BOT_TOKEN`, works
  even if the Telegram interface isn't the one currently running.
- **Sandboxed script execution** (`SANDBOX_ENABLED=true`, off by default):
  lets Orion write and run short Python scripts for one-off automation.
  Uses an isolated Docker container if `pip install docker` and a Docker
  daemon are available, otherwise falls back to a plain resource-limited
  subprocess (not a hard security boundary in that case) — read
  `tools/sandbox_tools.py`'s docstring before enabling.

## 10. Reasoning, dev tools & safety extras

- **Semantic memory**: `pip install -r requirements-memory.txt` (downloads
  a small local embedding model, no API key, runs fine on a Pi). Adds
  `index_memory`/`search_memory` — recall by meaning, not exact wording,
  beyond what `remember_fact`'s short facts cover.
- **Sub-agent delegation**: no setup — `delegate_to_subagent` is always on.
  Splits a big request into focused pieces (a 'researcher' pass, then a
  'writer' pass) using separate one-shot Claude calls.
- **Natural-language SQL**: `SQL_CONNECTION_STRING` (any SQLAlchemy URL —
  install the matching driver for non-SQLite databases). Read-only by
  default; Claude writes the SQL itself, no separate text-to-SQL model.
- **Code security audit**: no setup — `audit_code_security` (bandit) and
  `check_dependency_vulnerabilities` (OSV.dev, free/keyless) are always on.
- **Named deploy/build commands**: `DEPLOY_COMMANDS` as JSON
  (`{"build": "make build"}`) — deliberately not arbitrary shell access,
  only pre-approved named commands can run.
- **Expressive voice**: `ELEVENLABS_API_KEY` replaces local Piper in the
  voice interface with a cloud voice that shifts tone for urgent alerts
  vs. normal replies.
- **Kill switch**: `KILL_SWITCH_PHRASE` — a secret phrase that, said or
  typed exactly, wipes local memory/history and cached OAuth tokens.
  Unset (default) disables the kill switch entirely.
- **Credential leak checking**: `check_password_leaked` needs no key (uses
  k-anonymity — the password itself is never transmitted); email breach
  checking needs a paid `HIBP_API_KEY`.
- **Image analysis**: no setup — `analyze_image` sends a local image file
  to Claude's vision for critique/description (design mockups, screenshots,
  photos). No camera needed, since it works from a file, not a live feed.

## 11. Talking to Orion straight from the phone, no Telegram — Termux

§6 (Telegram) is the reliable, recommended way to reach Orion from
Android. This is a second, more direct option for when you'd rather have a
home-screen button that starts a spoken conversation, with nothing running
on a server — Orion's core runs *on the phone itself*, via
[Termux](https://termux.dev/) (a real terminal + Python environment for
Android, no root needed).

**How it avoids the heavy ML stack**: instead of faster-whisper/Piper/
openWakeWord — which are unlikely to have prebuilt wheels for Termux's
environment and would be painful to compile on a phone — this uses
Android's *own* built-in speech recognition and text-to-speech through the
Termux:API app (`termux-speech-to-text` / `termux-tts-speak`). Orion's
own dependencies (`anthropic`, `httpx`, ...) are otherwise ordinary
lightweight Python packages.

Setup:

1. Install **Termux** and **Termux:API** from
   [F-Droid](https://f-droid.org/) — specifically F-Droid, not the Play
   Store versions, which are outdated and break Termux:API.
2. In Termux:
   ```bash
   pkg install python termux-api git rust binutils
   git clone <your fork/branch of this repo> orion
   cd orion/orion
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
   `rust` and `binutils` are there for `jiter` and `pydantic-core` — two
   Rust-based packages that `anthropic` itself depends on. PyPI ships
   prebuilt wheels for them on desktop Linux/macOS/Windows but not for
   Termux's Android/Bionic environment, so pip falls back to compiling
   them from source, which needs a Rust toolchain present *before* you run
   `pip install`. Installing `rust`/`binutils` first avoids the
   `Failed to build 'jiter'` / `Failed to build 'pydantic-core'` errors —
   if you already hit one, just run `pkg install rust binutils` now and
   re-run `pip install -r requirements.txt`; pip resumes from where it
   left off.

   Other, non-essential packages may still fail to install on Termux (no
   prebuilt wheel for Android, and no local compiler for that one). That's
   fine — the same plugin architecture used everywhere else in this
   project means any tool whose dependency didn't install just silently
   stays disabled; the rest still works.
3. `cp .env.example .env`, fill in `ANTHROPIC_API_KEY`.
4. `python -m interfaces.termux.orion_termux` — Android's speech
   recognition prompt appears, speak, and Orion answers out loud.
5. Optional, for a home-screen button: install the **Termux:Widget** app
   (also F-Droid), then:
   ```bash
   mkdir -p ~/.shortcuts
   cp interfaces/termux/orion.sh ~/.shortcuts/Orion.sh
   chmod +x ~/.shortcuts/Orion.sh
   ```
   Add the Termux:Widget widget to your home screen and pick "Orion" —
   one tap starts a conversation.

**Honest limitation, stated plainly**: this is tap-to-talk, not hands-free
wake-word like the Pi. Android doesn't allow a background script to listen
continuously for a wake word without a dedicated foreground-service app,
which this isn't — so starting requires one tap (or running the script).
Once started, though, it keeps listening turn after turn on its own — you
don't need to tap again between exchanges — until you go quiet or say
"stop" (or "arrête"), so a single tap gets you a real back-and-forth
conversation, just not one that starts itself.

## What's deferred (from the full integration wishlist)

Some requested integrations aren't in yet, on purpose:

- **Phone calls** (answering, filtering, transcribing): in Switzerland,
  recording a conversation without every participant's consent is a
  criminal offense (Art. 179ter CP). A dedicated Twilio-based Orion phone
  line with an upfront recording disclosure (like any business "this call
  may be recorded" line) would be legal and is the planned approach — real
  phone-line interception is not.
- **Live camera vision** (OCR/object/barcode detection from a webcam feed,
  facial recognition): `analyze_image` (§10) now covers the *file-based*
  half of this — critique or describe any image you already have — but
  nothing here watches a live camera feed. Facial recognition specifically
  is still held for explicit confirmation given its biometric/privacy weight.
- **PC-level system control** (app launching, shutdown/lock, window
  management, keystroke emulation, Stream Deck): these only make sense if
  an Orion interface runs *on* the PC being controlled, not just the
  Pi/phone — and several (input emulation, remote shutdown) need a
  deliberate security decision before being wired up.
- **Apple Music, Amazon price tracking, game console control**: no
  legitimate public API exists for third-party control of these; building
  them would mean scraping or reverse-engineering private endpoints, which
  isn't something this project does.
- **Anti-bot-resistant scraping**: deliberately not built — tooling meant
  to evade a site's bot detection is designed to circumvent access
  controls, which isn't something this project does. Ordinary scraping
  (`fetch_webpage`) is unaffected.
- **Fully autonomous multi-person email negotiation / auto-send**: Orion
  drafts and triages (archive/label/mark-read), but never sends mail on its
  own — the same reasoning as the phone-call consent issue: an autonomous
  agent sending real messages to real people without review is a blast
  radius worth keeping a human in the loop for.
- **Live fact-checking on a meeting interlocutor**: would require recording
  and analyzing another person's speech in real time — the same Swiss
  consent-law issue (Art. 179ter CP) as the phone-call feature.
- **Full VM-per-execution isolation, offline local-model failover,
  multi-server 99.99% redundancy, a visual workflow engine**: all
  legitimate ideas, all disproportionate to what a personal assistant needs
  — `run_python_snippet` already isolates via Docker when available, and
  Orion's own tool-calling loop already *is* the automation orchestrator.
- **Discord/Slack bots, Twilio phone line, Plex/Kodi, OBS replay buffer,
  AudD music recognition, eye-tracking, gesture control, BCI, robotic arm
  control, AR glasses, haptics**: technically buildable (software ones) or
  hardware-dependent (the rest) — ask for any specifically and the
  software ones can follow the same pattern as everything else here.

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
  SQLite file (`ORION_DB_PATH`) — nothing is synced anywhere.

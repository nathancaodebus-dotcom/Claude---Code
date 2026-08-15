# Orion

**O.R.I.O.N. — Omniscient Reconnaissance & Intelligence Network.**

A personal AI assistant you can talk to about anything, at any time — it
reads your email, manages your calendar, controls your smart home, creates
and edits PowerPoint/Word/Excel files on request, controls Spotify and casts
video to your TV, and remembers things about you across conversations. One
agent core, five interfaces (terminal, Telegram voice conversations on
Android, a Termux tap-to-talk shortcut also on Android, always-listening
voice on a Raspberry Pi, and a HUD-styled local web UI) — anything you
dictate out loud goes through the same tool-using loop as typed text.
**Phone and Pi are both fully operational voice interfaces**, not one
primary and one afterthought — see §6/§11 for the phone and §7 for the Pi.

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
    web/app.py         # HUD-styled local browser UI — see §18
  systemd/         # unit files to run interfaces as background services on the Pi
```

Adding a new capability means writing one `Tool` subclass in `tools/` and
registering it in `tools/registry_builder.py` — nothing else changes.

## What Orion can do out of the box

Around 90-160 tools depending on configuration, registered in
`tools/registry_builder.py`:

| Category | Tools |
|---|---|
| Memory | remember/recall durable facts and preferences; log/list corrections distilled into a "lessons learned" digest over time (see "How Orion learns" below); **semantic memory** (search_memory/index_memory, §10) for recalling something by meaning, not exact wording |
| Email & calendar *(needs Google setup, §2)* | search/read Gmail, draft emails, **archive/mark-read/count unread** (triage, never auto-sends), list/create Google Calendar events, search/add contacts |
| Outlook / Microsoft 365 *(needs Azure app registration, §15)* | same shape as the Google row above but for Outlook Mail/Calendar/Contacts via Microsoft Graph — search/read/draft mail (never auto-sends), archive/mark-read/count unread, list/create calendar events, search/add contacts |
| **Shopify** *(needs a custom app token, §16)* | run real parts of an e-commerce business — list/view/fulfill orders, sales summaries, create/update products, manage stock, search customers, create discount codes. Deliberately no refunds or order cancellation, see §16 for why |
| Other calendars *(§9)* | list/create events on **any CalDAV calendar** — Outlook, iCloud, Nextcloud |
| Task managers | built-in to-dos, or **Todoist** (§9) if that's where you already live |
| Notes | built-in notes, or straight into your **Obsidian vault** (§9) as markdown, with note listing/search by title |
| Smart home *(needs Home Assistant, §3)* | list devices, control any light/switch/climate entity |
| Productivity | to-dos, notes, shopping list, reminders & timers, project/milestone tracking, **meeting briefing dossiers** (prep on a person/company before a meeting) |
| **Documents** | **PowerPoint** — slides, images, speaker notes; **Word** — paragraphs, headings, tables, images, page breaks; **Excel** — rows, formulas, charts, cell formatting (bold/color/number format), multiple sheets — all by voice or text; **read** existing PDF/Word/any text or code file; **interactive charts** (Plotly) — bar/line/scatter/pie/histogram, single or multi-series |
| **Websites** *(§13)* | create/edit a static site (plain HTML/CSS, multi-page, consistent nav, embed images) by voice or text, then **publish it live** to GitHub Pages for free, or to Infomaniak (paid, Swiss) over SFTP — local-only until you ask to publish |
| **Images** *(§14)* | **generate** from a text prompt, up to 4 variations per call (needs `GEMINI_API_KEY`, paid, see the cost caveat there) or **edit** an existing file — resize/crop/rotate/filters (grayscale/sepia/invert/blur/sharpen)/adjustments/text overlays/collages, no API key needed |
| **Video** *(§14)* | **edit** an existing file — trim, concatenate, extract/replace audio, convert format, change speed, extract a frame, burn in captions or a watermark — via ffmpeg, no API key needed. Generating video from scratch isn't built yet, see §14 for why |
| **Music** *(needs Spotify setup, §4)* | search, play, pause, resume, skip, volume, create/fill playlists, list Spotify Connect devices |
| **Video / casting** *(needs Chromecast setup, §5)* | discover Chromecasts, search & play YouTube videos, launch Netflix/Disney+/Spotify/YouTube Music on the TV — see the caveat in §5 |
| Live info | weather (+ historical comparison), sunrise/sunset, Wikipedia, dictionary, currency, stocks, crypto, news, RSS, Reddit, GitHub watching, upcoming movies |
| **Crypto trading & quant research** *(§12 — research/paper-tracking only, see the caveat there)* | market data, side-by-side comparison, technical indicators (SMA/RSI/volatility), a two-portfolio paper tracker with **propose → user confirms → applies** for every position change — never places a real order; fee-aware P&L, fixed-fractional position sizing (`suggest_position_size`); **quantitative signal backtesting** (Rank IC + Sharpe/Sortino/win-rate/drawdown against real historical stock prices, run in the sandbox) |
| Open web | web search, fetch & read a webpage, shorten a URL, public IP, service uptime checks |
| Utilities | calculator, unit conversion, password generator, QR codes, ambient noise generator, **flashcard/quiz generator** (real Anki .apkg files, basic question/answer or cloze-deletion cards) |
| **Dev tools** *(§10)* | **natural-language SQL queries** (read-only by default), **code security audit** (bandit + OSV vulnerability lookup), **named build/deploy commands**, **sub-agent delegation** (researcher/coder/writer/critic) |
| System / files | CPU/temp/memory/disk/uptime, **top processes + priority control**, **disk health (SMART)**, find large/duplicate files, local backups, network speed test, failed-command log |
| Automation | run short Python scripts on demand (Docker-isolated if available, else subprocess) — off by default |
| Safety | emergency alert with location, **kill switch** (wipe local data on a confirmation phrase), **credential leak checking** (HIBP) |
| Vision | **analyze/critique a supplied image** (design mockups, screenshots, photos — no camera needed, works on any image file) |
| Just for fun | coin flip, dice, 8-ball, quotes, jokes, song lyrics, YouTube transcripts/summaries |
| **Briefings** | `morning_briefing`, `evening_debrief`, `prepare_meeting_briefing` |
| **Offline fallback** *(§17, needs Ollama installed separately)* | automatic only — switches to a local model when Claude is genuinely unreachable (no connection, an outage, empty account balance), with a curated subset of tools that need no network; never on its own initiative, every reply says so plainly |

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

Worth being precise about what "learns" means here: this is all in-context
memory — persisted facts and summaries re-read into the prompt every turn —
not weight-level training. The Anthropic API doesn't expose a fine-tuning
endpoint for Claude models to regular API customers, so there's no way for
Orion's underlying model to actually update from corrections the way a
trained ML model would. Everything below is the practical, honest substitute:
software that makes the in-context memory behave as much like "learning from
mistakes" as an architecture without weight updates can.

Memory here works on four tracks, all automatic — none require the user to
say "remember this":

- **Facts and preferences** (`core/memory.py`, the `facts` table): the
  system prompt instructs the model to call `remember_fact` whenever it
  notices something durable worth keeping — stated facts as well as
  preferences it infers. Global, visible to every interface and session.
- **Corrections and "lessons learned"** (`core/memory.py`'s `corrections`
  table, `core/correction_synthesis.py`): distinct from facts on purpose.
  When the user corrects how Orion did something — wrong tone, wrong
  assumption, wrong tool choice — the system prompt instructs it to call
  `log_correction` instead, capturing the mistake and what to do instead as
  its own record rather than one more fact among many. If `search_memory`
  is available (§10), each correction is also indexed there so a related
  correction can surface contextually, by meaning, even when it isn't in
  the recent tail. Raw corrections would eventually clutter the prompt, so
  once more than a dozen accumulate, the oldest ones get folded into a
  compact "lessons learned" digest via one extra Claude call — merging
  repeated corrections into a general rule instead of keeping every
  individual instance — the same distillation `core/consolidation.py` does
  for conversation history, just for mistakes specifically. Both the digest
  and any not-yet-folded recent corrections are injected into the system
  prompt every turn.
- **Conversation assimilation** (`core/consolidation.py`): `Memory.history()`
  only ever sends the most recent ~40 messages to the model, so a long
  running conversation would normally just lose everything older than that.
  Instead, once a session passes 60 messages, the oldest overflow gets
  folded into a running per-session summary via one extra Claude call —
  merged with whatever was summarized before — so the gist of a long
  relationship survives even after the raw messages scroll out of context.
  This is triggered at the end of every `Agent.respond()` call but runs in
  the background, so it never delays the answer you're waiting for.
- **Lookup results** (`core/tool_cache.py`): when a read-only tool looks
  something up (weather, a web search, a dictionary definition, ...), the
  answer is kept for as long as that kind of information stays valid, so
  asking again shortly after reuses it instead of looking it up again from
  scratch — the closest thing here to "learned something new, remembers it
  next time." Unlike the other tracks, this is a speed optimization scoped
  to one running process, not a durable store — it resets on restart and
  only applies to safe-to-cache lookups (see the "Response speed" section
  below for exactly which tools and why).

All four are visible in code — `recall_facts`, `list_corrections`, the
"Summary of earlier conversation" and "Lessons learned" blocks Orion sees in
its own system prompt, and `core/tool_cache.py`'s `CACHEABLE_TOOLS` map —
nothing here is hidden state.

## 1. Setup

```bash
cd orion
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**On Windows** (PowerShell), the only difference is how the virtualenv is
activated and copying `.env`:

```powershell
cd orion
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

(If PowerShell refuses to run the activation script with an "execution
policy" error, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
once, or activate via `.venv\Scripts\activate.bat` in cmd.exe instead.)
Everything else in this README — every `python -m ...` command, every
`.env` variable — is identical on Windows; only shell syntax for
activating the venv and installing OS packages (ffmpeg, etc.) differs,
called out inline below where it comes up.

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
   text-to-speech: `ELEVENLABS_API_KEY` (cloud, best quality, works
   anywhere this bot runs, no local model needed), a local Piper model as
   described in §7 if this bot happens to run on the same machine as the
   voice loop, or — if you set up neither — Orion tries Edge TTS
   automatically (free, no API key, no model file; just needs `edge-tts`
   installed and internet). Without any of the three, voice messages still
   work — you just get a text reply instead of a spoken one.
4. Install [ffmpeg](https://ffmpeg.org/) (`apt install ffmpeg` on
   Debian/Raspberry Pi OS, `brew install ffmpeg` on macOS, `winget install
   ffmpeg` or `choco install ffmpeg` on Windows — or download a build from
   ffmpeg.org and add it to your `PATH` manually) — needed to encode
   replies into the Opus format Telegram requires for voice notes. Without
   it, replies fall back to text.
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

## 7. Always-listening voice

Works the same way on a Raspberry Pi, a Linux/macOS machine, or Windows —
for the closest experience to actually talking to Orion out loud:

```bash
pip install -r requirements-voice.txt
```

**On Windows**, this installs cleanly with no extra system package —
`sounddevice`'s wheel already bundles PortAudio (unlike Debian/Raspberry
Pi OS, where `sudo apt install libportaudio2` is sometimes needed
separately; not applicable here).

Download a [Piper](https://github.com/rhasspy/piper/blob/master/VOICES.md)
voice model for your language into `~/.local/share/piper/` (e.g.
`fr_FR-siwis-medium.onnx` for French). On Windows this is
`C:\Users\<you>\.local\share\piper\` — `Path.home()` resolves there the
same way, it's just not the OS-idiomatic location; create the folder
manually (`mkdir $env:USERPROFILE\.local\share\piper` in PowerShell) and
drop the `.onnx` file in.

**Don't want to do the Piper download right now?** `python -m
interfaces.voice.voice_loop` still works without it: with no
`ELEVENLABS_API_KEY` and no Piper model found, Orion falls back to Edge
TTS automatically — Microsoft's free cloud voice, no API key, no model
file, just `pip install edge-tts` (already in `requirements-voice.txt`)
and an internet connection. Lower priority than Piper once you do set a
model up (Piper is fully offline; Edge TTS isn't), but a genuinely
zero-setup way to hear Orion talk on a fresh install. `EDGE_TTS_VOICE`
already defaults sensibly for `VOICE_LANGUAGE=fr`/`en`; set it directly to
change the voice or use another language (`edge-tts --list-voices`).

```bash
python -m interfaces.voice.voice_loop
```

Say the wake word (`WAKE_WORD` in `.env`), then speak your request; Orion
answers out loud.

**"Hey Orion" actually works.** openWakeWord ships no pretrained model for
that phrase itself (its bundled models are alexa, hey_mycroft, hey_jarvis,
timer, weather), so a custom one was trained specifically for this project —
see `scripts/wake_word_training/README.md` for exactly how (short version:
openWakeWord's official recipe leans on Hugging Face for its training data,
which isn't reachable from where this was built, so it's trained on Google
Speech Commands as a substitute negative dataset instead). It ships at
`wake_word_models/hey_orion.onnx`, and the `WAKE_WORD=hey_orion` default
resolves to it automatically — no extra setup needed.

Being trained on a smaller, less varied substitute dataset than the official
recipe calls for, this is a real but imperfect baseline — the actual
validation numbers from this training run: **76% accuracy, 53% recall,
~30 false positives/hour** on held-out data. In plain terms: when it
triggers, it's almost always right, but it'll also miss roughly half of
genuine "Hey Orion" attempts, and may occasionally trigger on nothing in
particular (recall and false-positive rate both improve significantly by
retraining with real voice samples, since the current model has *only*
ever heard synthetic TTS speech). The single best way to sharpen it is
adding real recordings of your own voice saying "Hey Orion" (easiest via
Telegram voice notes) and retraining; see "Improving the model with real
recordings" in that same README. If it's unreliable enough to be annoying
in the meantime, `WAKE_WORD=hey_jarvis` switches back to openWakeWord's own
working built-in model while you improve it.

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
wrong for most rooms/mics.

**Saying the wake word again while Orion is talking interrupts it
(barge-in) — off by default.** `VOICE_BARGE_IN_ENABLED=true` turns it on.
It used to be a plain volume check on the same mic Orion's own voice
plays out of, which — with no real acoustic echo cancellation — made a
laptop's built-in speakers and mic (inches apart) reliably hear *Orion's
own reply* as the user talking over it and cut itself off mid-sentence
for no reason. Requiring the actual wake word instead of just "some
noise" (the same openWakeWord model already used to wake Orion up in the
first place, listening throughout playback instead of only when idle) is
far less prone to that — Orion's own synthesized reply text essentially
never sounds like "hey orion" to it — but it's not a hard guarantee
against self-triggering the way headphones or real AEC would be, which
is why it still needs an explicit opt-in rather than being on by
default.

**If replies feel slow to start**, the biggest lever on a CPU-only laptop
is the transcription model: `WHISPER_MODEL_SIZE` in `.env` defaults to
`small` (the most accurate that's still reasonably fast); try `base` or
even `tiny` — each step down roughly halves transcription time, at some
cost to recognizing uncommon words/names. There's no local GPU
acceleration wired in here — faster-whisper always runs on CPU
(`device="cpu"` in `interfaces/voice/voice_loop.py`) regardless of what
hardware is available, so this is the main knob until that changes.

**If Orion keeps cutting you off after under a second, or answers with
something bizarre like "sous-titres" or "thanks for watching!"** that you
never said, two related things are going on. The console prints your
mic's calibrated level on every start (`Ambient noise level: X — silence
threshold set to Y`) — if `X` is very low (single digits), your
microphone's input volume is probably turned down at the OS level, not
too quiet to matter: on Windows, Settings → System → Sound → Input →
pick the right device → raise Volume, and check Device Properties →
Levels → "Microphone Boost" too (often 0 dB by default on laptops). A
mic that's too quiet cuts recording short before you've really started
talking, which starves faster-whisper of real audio to work with — and
Whisper's known failure mode on near-silent/too-short clips isn't an
empty result, it's confidently hallucinating plausible-sounding
boilerplate it saw a lot of during training (subtitle-credit phrases
like "Sous-titres réalisés par la communauté d'Amara.org" are extremely
common examples, in French specifically). `core/stt.py` filters these
out using Whisper's own per-segment `no_speech_prob` rather than a
hardcoded phrase list, so a bad recording now correctly comes back as
"nothing understood" instead of confidently wrong text — but raising
your mic's input level is still the real fix for the short-recording
problem underneath it.

## 8. Running as background services

**On Linux** (Raspberry Pi or otherwise):

```bash
sudo cp systemd/orion-telegram.service systemd/orion-voice.service systemd/orion-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now orion-telegram orion-voice orion-web
```

Edit the `User=`, `WorkingDirectory=` and venv path in the unit files first
if your setup differs from `/home/pi/orion`. All three are independent —
enable only the ones you actually want running as background services;
`orion-web` still needs `pip install -r requirements-web.txt` done first
(§18) or it'll restart-loop on the missing `fastapi`/`uvicorn` imports.
Since the web UI binds to `127.0.0.1` only (§18), reach it from another
device on the same network with an SSH tunnel:
`ssh -L 8420:127.0.0.1:8420 pi@<pi-address>`, then open
`http://127.0.0.1:8420` on your own machine.

**On Windows**, systemd doesn't exist — `scripts/windows/install_orion_tasks.ps1`
registers the same three interfaces as Scheduled Tasks instead, the closest
Windows equivalent (auto-start at logon, auto-restart on failure):

```powershell
cd orion
.\scripts\windows\install_orion_tasks.ps1
```

(If PowerShell blocks it with an execution-policy error, same fix as venv
activation in section 1: `powershell -ExecutionPolicy Bypass -File
.\scripts\windows\install_orion_tasks.ps1`.) This registers `Orion-Web`,
`Orion-Telegram`, and `Orion-Voice`, each running
`.venv\Scripts\pythonw.exe -m <interface module>` (`pythonw`, not `python`
— no console window popping up at every logon) with the repo folder as its
working directory, triggered at your next logon under your own user
account, restarting up to 999 times a minute apart if one crashes. Pass
`-Interfaces web,telegram` to register only a subset. Manage them
afterwards from Task Scheduler (`taskschd.msc`) or PowerShell
(`Get-ScheduledTask -TaskName 'Orion-*'`, `Start-ScheduledTask -TaskName
'Orion-Web'` to start one immediately instead of waiting for next logon,
`Get-ScheduledTaskInfo -TaskName 'Orion-Web'` for last run result). Run
`.\scripts\windows\uninstall_orion_tasks.ps1` to remove all three.

Requires the venv to already exist with dependencies installed first
(section 1) — the install script checks for `.venv\Scripts\pythonw.exe`
and errors with that reminder if it's missing, rather than registering a
task that would just fail silently at logon. `.env` is picked up the same
way as everywhere else (`core/config.py`'s `load_dotenv()` finds it from
the working directory), so there's no separate step to hand it to the
task the way `EnvironmentFile=` does for systemd.

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
- **Proactive health monitoring**: no setup — `core/health_monitor.py`
  watches the same failure log `list_failed_commands` reads from, and
  pushes an alert (same channel as reminders: printed on CLI, spoken on
  the voice loop, a Telegram message) the moment a tool has failed 3+
  times in the last hour, instead of waiting for you to notice something's
  broken and ask. Re-alerts on the same tool are capped at once per 6
  hours so a sustained outage doesn't spam you, and a failed delivery
  (e.g. a network blip) retries on the next poll rather than being lost
  until the cooldown clears.

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

## 12. Crypto trading — research and paper portfolio only

**Read this before using it.** No autonomous, unsupervised trading was
built here — deliberately. There's no exchange or broker integration in
this codebase at all: nothing here can place a real order, on any
platform, under any circumstance. What's actually here is a research and
decision-support layer, backed by a paper (simulated) portfolio, no setup
or API key required:

- `get_crypto_market_data` / `compare_crypto_assets` — live price, 24h
  change, market cap, and volume, for one coin or several side by side.
- `get_crypto_technical_indicators` — 7-day and 30-day simple moving
  averages, 14-day RSI, and recent daily-return volatility for a coin.
  Reports raw numbers only; Orion still has to reason about what they mean
  for your actual question, same as it would for any other data.
- Two (or however many you want) named paper portfolios — e.g. `stable`
  for long-term/lower-risk positions, `risky` for the fast, frequent kind
  — tracked with **`propose_crypto_trade` → you decide →
  `confirm_crypto_trade` or `reject_crypto_trade`**. Proposing a trade
  fetches the live price itself (never a number Claude supplies), but
  changes nothing until you explicitly confirm it. `list_crypto_holdings`
  shows live unrealized P&L against your average buy price;
  `list_pending_crypto_trades` shows what's awaiting your decision.
- Every proposal carries an estimated trading fee (`fee_pct`, default
  0.1% — a typical major-exchange taker fee, adjustable per proposal) so
  the paper P&L doesn't look artificially better than a real account
  would — the same realism backtesting frameworks like Freqtrade insist
  on. On confirm, a buy's fee is folded straight into the cost basis
  (`avg_buy_price_usd` reflects what you actually paid, fee included); a
  sell's fee is reported back but not applied to any balance, since this
  project keeps no cash-balance/proceeds ledger.
- `suggest_position_size` — pure fixed-fractional risk-sizing math
  (portfolio value, entry price, stop-loss price, risk % → suggested
  position size), the standard approach frameworks like Freqtrade default
  to: risk a small, fixed slice of the portfolio per trade, sized so
  hitting the stop costs exactly that slice. No network call, no coin
  reference — just the calculation, informational only.

**Why it stops there.** No LLM-driven system — this one included — has a
track record of reliably beating the market autonomously; markets are
adversarial, and a model can misread a number, hallucinate, or (if it's
ever wired to browse the live web for "research") get steered by
manipulated content it reads along the way. Combine that with unsupervised
execution on real money, especially at high frequency on a volatile asset,
and mistakes compound fast with no one watching. Keeping a human
confirmation step on every position change is the same design choice this
project already makes for Gmail (drafts and triages, never auto-sends) —
applied to something with a more immediate, harder-to-reverse cost.

If you build or wire up real exchange execution yourself on top of this,
treat the paper-tracking numbers here as informative, not validated —
they've never been tested against real capital, slippage, fees, or a live
order book.

**Quantitative signal research** (`tools/quant_signal_tools.py`, no setup
required): the same idea as NVIDIA's Quantitative Signal Discovery Agent
blueprint — propose a formula, test whether it actually predicted future
returns, keep the ones that work — built without the GPU/NIM stack that
blueprint needs, since the "idea generation" step is just Claude reasoning
in conversation.

- `backtest_quant_signal` — give it a ticker and a signal written as
  Python (`def signal(bars): ...`, stdlib only, no pandas/numpy), and it
  fetches real historical prices (stooq.com, the same free source
  `get_stock_price` uses), runs the signal **inside the existing sandbox**
  (§10 — a model-authored formula is untrusted input, same as a
  user-authored script), and reports its **Rank IC** (Spearman correlation
  between the signal and the N-day-forward return) — the standard measure
  of a signal's predictive power. Raw number only, no verdict — same
  philosophy as the technical indicators above. It also reports standard
  performance metrics (win rate, Sharpe, Sortino, profit factor, max
  drawdown — the same metrics Backtrader/QuantConnect report) for a naive
  "long when the signal is above its own median" strategy, when there's
  enough above-median history to compute them. These use overlapping
  windows, not a rigorous walk-forward backtest — indicative, not a
  substitute for a real backtesting engine.
- `save_quant_signal` / `list_quant_signals` — keep the formulas that
  backtested well, ranked by IC, for later reuse.

Pure research: nothing here places a trade, same as everything else in
this section. These additions borrow specific, safe ideas from mature
open-source trading projects (Freqtrade's fee realism and risk-per-trade
sizing, Backtrader/QuantConnect's standard performance metrics) — never
their live-execution engines. Freqtrade, Hummingbot, and StockSharp are
built around actually placing orders on an exchange; Nautilus Trader's
core value is a real-time event engine for live trading. None of that fits
here, on purpose, for the same reason stated above.

## 13. Website creation

Ask Orion to create a site and it writes plain HTML/CSS straight to disk —
no framework, no build step, no external font/CDN dependency, so pages
load instantly and there's nothing to break. Every page shares one clean,
responsive, dark-mode-aware CSS baseline (`tools/website_tools.py`); Claude
supplies each page's actual content as semantic HTML, so wording and
structure are still fully under your control, just wrapped in a
consistent, tested-looking shell.

```
"crée-moi un site pour mon portfolio, avec une page d'accueil et une page contact"
"ajoute une page 'projets' avec une liste de mes trois derniers projets"
"change le texte de la page contact"
```

- `create_website` — one or more pages, returns the `site_name` for later
  `add_website_page` / `edit_website_page` / `delete_website_page` /
  `list_website_pages` calls, same pattern as the presentation/document
  tools. Every page in a site links to every other page in its nav, so
  adding or removing a page regenerates all of them, not just the one that
  changed.
- Output lands in `outputs/websites/<site_name>/` — open `index.html` in
  any browser to view it, no server needed.

**Creating a site only writes local files — nothing is online until you
publish it.**

- `publish_website_to_github_pages` — free. Needs `GITHUB_PAGES_TOKEN` (a
  [personal access token](https://github.com/settings/tokens) with `repo`
  scope) and `GITHUB_PAGES_OWNER` (your GitHub username or org). Creates a
  repo named after the site if one doesn't exist yet, pushes every file,
  and enables Pages — returns `https://<owner>.github.io/<site_name>/`.
  Can take a minute to actually go live after the tool returns.
- `publish_website_to_infomaniak` — paid, Swiss hosting, over SFTP. Needs
  `INFOMANIAK_FTP_HOST`/`INFOMANIAK_FTP_USERNAME`/`INFOMANIAK_FTP_PASSWORD`
  from your [Infomaniak Manager](https://manager.infomaniak.com/) (Web
  Hosting → your hosting → FTP/SFTP access), and the `paramiko` package
  (already in `requirements.txt`, guarded the same way Pillow/numpy/qrcode
  are elsewhere — if it fails to build on a given machine, this tool just
  reports that clearly instead of the whole assistant crashing). Uploads
  every file under an optional `remote_dir` (defaults to a folder named
  after the site) — point your domain/subdomain's docroot at it in the
  Infomaniak Manager to go live.

## 14. Image and video generation/editing

**Editing needs no API key or setup** — `tools/image_edit_tools.py`
(Pillow) and `tools/video_edit_tools.py` (ffmpeg, already required for
Telegram voice replies) work on any existing image/video file the moment
Orion has a path to one (uploaded via Telegram, or already on disk):

- Images: `edit_image` (resize, crop, rotate, grayscale, blur, sharpen,
  brightness/contrast/saturation) and `add_text_to_image` (captions,
  watermarks).
- Video: `trim_video`, `concatenate_videos`, `extract_audio_from_video`,
  `add_audio_to_video` (replace the audio track — background music, a
  voiceover), `convert_video_format`, `add_caption_to_video` (burned-in
  text, not a toggleable subtitle track).

**Image generation is a paid API call**, via Google Imagen through the
Gemini API — a separate key (`GEMINI_API_KEY`) from `ANTHROPIC_API_KEY`,
[no free tier](https://ai.google.dev/gemini-api/docs/pricing), a few cents
per image. `generate_image` only registers as a tool when this key is set,
so it's simply absent rather than failing at call time if you haven't set
one up — get a key at https://aistudio.google.com/apikey.

**Video generation isn't built.** Google's Veo API is the natural
counterpart to Imagen here, but it has no free tier at all and bills per
*second* of output — up to $0.60/s depending on model and resolution, so a
single 10-second clip can run several dollars. That's a real, ongoing cost
with no built-in limit, which is exactly the kind of thing this project
adds guardrails for before turning on (see §12's reasoning for crypto
trading) rather than wiring up quietly. Worth building once there's an
explicit ceiling on cost (a max clip length, a per-day cap, or similar) —
ask when you want to set that up.

## 15. Microsoft 365 (Outlook Mail/Calendar/Contacts)

Same shape as §2's Google integration, alongside it rather than replacing
it — use whichever account (or both) makes sense for a given request.
Setup uses a device-code sign-in instead of a browser popup, since Orion
usually runs headless on the Pi:

1. In [Entra ID / Azure AD](https://entra.microsoft.com/) → **App
   registrations** → **New registration**. No redirect URI is needed —
   this uses the OAuth device code flow, not a browser callback.
2. Under **Authentication**, enable **"Allow public client flows"** (this
   is what lets Orion sign in without a client secret).
3. Under **API permissions**, add these Microsoft Graph delegated
   permissions: `Mail.Read`, `Mail.ReadWrite`, `Calendars.ReadWrite`,
   `Contacts.ReadWrite`. `Mail.Send` is deliberately not requested — same
   "drafts and triages, never auto-sends" boundary as Gmail (§2).
4. Copy the app's **Application (client) ID** into `MICROSOFT_CLIENT_ID`
   in `.env`.
5. Run `python -m interfaces.cli` and ask Orion to check your Outlook
   inbox — on first use it prints a URL and a short code; enter both from
   any device (phone, laptop) to authorize. The token is then cached to
   `MICROSOFT_TOKEN_PATH` so it never asks again.

Tools (`tools/outlook_tool.py`, `tools/microsoft_calendar_tool.py`,
`tools/microsoft_contacts_tool.py`): `search_outlook_emails`,
`read_outlook_email`, `create_outlook_email_draft` (never sends),
`archive_outlook_email`, `mark_outlook_email_read`,
`count_unread_outlook_emails`, `list_outlook_calendar_events`,
`create_outlook_calendar_event`, `search_outlook_contacts`,
`add_outlook_contact` — all registered only when `MICROSOFT_CLIENT_ID` is
set, same config-gating pattern as every other optional integration here.

## 16. Shopify (e-commerce store management)

Lets Orion run real parts of a Shopify-based online business: check and
fulfill orders, manage the product catalog and stock levels, look up
customers, create discount codes, and summarize recent sales — by voice
or text, from wherever you're talking to Orion.

1. In your Shopify admin: **Settings → Apps and sales channels → Develop
   apps → Create an app**.
2. Under **Configuration → Admin API integration**, grant these scopes:
   `read_orders`, `write_orders`, `read_products`, `write_products`,
   `read_inventory`, `write_inventory`, `read_customers`,
   `read_price_rules`, `write_price_rules`.
3. **Install the app**, then reveal and copy the **Admin API access
   token** (shown once).
4. Set `SHOPIFY_STORE_DOMAIN` (e.g. `your-store.myshopify.com`) and
   `SHOPIFY_ACCESS_TOKEN` in `.env`.

```
"combien de commandes non expédiées j'ai en ce moment ?"
"expédie la commande 1042 avec le numéro de suivi 1Z999AA1"
"crée un produit 'Mug Orion' à 19.90 CHF"
"remets le stock du t-shirt noir à 50"
"fais-moi un résumé des ventes des 7 derniers jours"
"crée un code promo BIENVENUE10, 10% de réduction"
```

Tools (`tools/shopify_tools.py`): `list_shopify_orders`,
`get_shopify_order`, `fulfill_shopify_order`, `get_shopify_sales_summary`,
`list_shopify_products`, `get_shopify_product`, `create_shopify_product`,
`update_shopify_product`, `update_shopify_inventory`,
`search_shopify_customers`, `get_shopify_customer_orders`,
`create_shopify_discount` — registered only when both
`SHOPIFY_STORE_DOMAIN` and `SHOPIFY_ACCESS_TOKEN` are set.

**Deliberately missing: refunds and order cancellation.** Both move money
back out or void a sale — the same category of action as auto-sending
email (§ Gmail) or executing a real crypto trade (§12), which this
project keeps a human in the loop for rather than letting an LLM do
unsupervised. Everything built here either reads data or takes a normal,
expected, reversible forward action (shipping a paid order, updating a
listing, restocking inventory, creating a discount) — nothing that
un-does a sale a customer already completed.

## 17. Offline fallback (local model via Ollama)

Every interface (CLI, Telegram, voice) shares one `Agent`, which tries
Claude first — always. Only if a Claude call fails for a specifically
offline-shaped reason does it automatically switch to a local model
instead:

- No network connection (`APIConnectionError`)
- Anthropic is rate-limiting or having an outage (`RateLimitError`,
  `InternalServerError`)
- The account is out of credit (the "Your credit balance is too low..."
  error)

It deliberately does **not** fall back on an authentication error or any
other `BadRequestError` — those mean something is actually
misconfigured (a bad API key, a malformed request), and silently
switching to a much less capable local model would just hide the real
bug instead of surfacing it. Every offline reply is prefixed with
`[mode hors-ligne] ` so it's never ambiguous which "brain" answered.

**This is a fallback, not a replacement.** An open-weight local model is
meaningfully less reliable than Claude at multi-step tool orchestration,
so this never becomes the default — it only activates automatically,
only when Claude is genuinely unreachable, and only exposes a curated
subset of tools that make no network call of their own (to-dos, notes,
reminders, remembered facts, local documents/spreadsheets/presentations,
local image/video edits, and similar — not Gmail, weather, Spotify, or
anything else that needs a service Ollama can't reach either). If the
user asks for something outside that set while offline, it says so
plainly rather than guessing.

Setup:

1. Install [Ollama](https://ollama.com) separately (it's not a Python
   dependency — a standalone local server).
2. Pull a model once: `ollama pull llama3.1:8b` (needs ~5 GB free disk
   and runs comfortably on 16 GB+ RAM; with 32 GB+ RAM, a larger model
   like `qwen2.5:14b` is also viable — set `OLLAMA_MODEL` to match
   whatever you pull).
3. That's it — `OLLAMA_HOST` (default `http://localhost:11434`) and
   `OLLAMA_MODEL` (default `llama3.1:8b`) are already set in
   `.env.example`. If Ollama isn't installed or isn't running, Orion just
   behaves exactly as it does today (a Claude failure surfaces as an
   honest error instead of a fallback) — no crash, no extra setup
   required to keep using Orion normally.

Tools (`core/offline_agent.py`, `tools/base.py`'s `Tool.requires_network`
flag): no new tools — this reuses the existing registry, filtered to
whichever tools have been explicitly reviewed and marked safe for a model
that can't reach the network at all.

## 18. HUD-styled local web UI

The same Orion — same `Agent`, same tools, same memory — behind a browser
tab instead of a plain terminal: a dark, glowing, sci-fi-HUD-inspired
interface (`interfaces/web/`), for anyone who wants something nicer to
look at than a scrolling `you>` prompt. This is an additional interface,
not a replacement — the CLI, Telegram, and voice loop are unaffected and
keep working exactly as before.

```bash
pip install -r requirements.txt -r requirements-web.txt
python -m interfaces.web.app
```

Then open **http://127.0.0.1:8420** (port configurable via
`ORION_WEB_PORT`). Deliberately no visible transcript — type a message and
there's no scrolling back-and-forth text log; instead Orion speaks the
reply out loud, sentence by sentence as each one is ready, using the same
TTS backends as Telegram and the voice loop (ElevenLabs if
`ELEVENLABS_API_KEY` is set, else a local Piper model per §7, else Edge
TTS automatically — nothing extra to configure if you already did §7). A
radial equalizer around the circle reacts while it plays, the same idea
as a microphone app's level meter, and the central emblem's glow speeds
up while thinking and pulses while replying. If no TTS backend is
configured at all, the equalizer still animates on its own — you just
won't hear anything, the same silent-but-working degradation a Telegram
voice message gets with no TTS set up. Reminders, health alerts (§9/§10),
errors, and anything a tool generates (an image, a QR code, a document)
all surface as brief HUD notification toasts — the input bar is still
there for typing, just nothing renders the conversation as text on screen.

Browsers restrict autoplaying audio to actions the user actually
triggered — since playback starts from the same click/Enter that sent the
message, this works in every browser tested, but if a reply ever plays
silently, that's almost certainly why (no error, no toast, just no
sound).

Single-user, single-session, same as the CLI — two browser tabs open at
once share one conversation, the same as running the CLI twice would with
the same `ORION_DB_PATH`. No auth, no HTTPS: it binds to `127.0.0.1` only
(not reachable from other devices on your network), which is the right
tradeoff for a personal tool running on your own machine, not a public
one.

Pure vanilla HTML/CSS/JS on the frontend — no framework, no build step,
no external font/CDN dependency (same philosophy as §13's website
generator) — so it's one `pip install` away from running and there's
nothing to break. The backend is a small FastAPI app that streams replies
over Server-Sent Events; `requirements-web.txt` is the only new
dependency (`fastapi`, `uvicorn`).

To keep it running in the background instead of a foreground terminal,
`systemd/orion-web.service` follows the same pattern as the Telegram/voice
units — see §8.

**Talking to it instead of typing**: click the 🎤 button once to start a
whole spoken back-and-forth, not just one recording. Each utterance stops
itself as soon as you go quiet — client-side silence detection in the
browser, the same idea as §7's Raspberry Pi voice loop's calibrated
silence detection, reimplemented in the Web Audio API since there's no
way to reuse that server-side Python against a live browser mic stream —
gets transcribed (faster-whisper, needs `requirements-voice.txt` per §7)
and sent exactly like typing it would be, and the mic reopens on its own
for the next turn once Orion's done replying. No re-clicking between
turns; click the 🎤 again any time to end the conversation (a manual click
while it's actively recording also stops that one utterance early, same
as before). Three failed turns in a row ends the conversation
automatically with an explanation rather than silently retrying forever
against something consistently broken. This is still not always-listening
like §7's voice loop — a browser tab can't keep a mic open unattended
waiting for a wake word the way a dedicated process can, so the initial
click is still needed; for genuinely hands-free use with no click at all,
run `interfaces.voice.voice_loop` instead (§7), separately from the web
UI.

The browser will ask for microphone permission the first time — if it
never asks, or the mic button shows an error immediately on click, check,
in order:
1. **The address bar says `http://127.0.0.1:8420` (or `localhost`)** —
   `getUserMedia` (the browser API this uses) refuses to run at all
   outside a "secure context," and plain `http://` only counts as one for
   `127.0.0.1`/`localhost` specifically, not any other address (a LAN IP
   like `192.168.x.x`, a hostname, etc.) — those would need HTTPS, which
   this project deliberately doesn't set up (§18 above).
2. **On Windows specifically**, a `NotAllowedError` toast even after
   granting the browser's own permission prompt usually means the *OS-level*
   toggle is off: Settings → Privacy & security → Microphone → make sure
   both the main toggle and "Let desktop apps access your microphone" are
   on. This is a Windows setting, not a browser one, and blocks every
   browser/app alike regardless of what's granted inside the browser.
3. **The browser's own per-site permission** — click the padlock/site-info
   icon in the address bar and check the microphone permission for this
   page hasn't been explicitly blocked from an earlier "Deny" click.

A `NotFoundError` toast instead means no microphone was found at all
(disabled/disconnected device, or a laptop's built-in mic disabled in
Windows Device Manager) — different fix than the permission cases above.

## 19. Cloud model routing (Haiku/Sonnet)

Every reply used to go through Sonnet, even "what time is it" or "hi" —
correct, but paying Sonnet's latency and cost for a question that doesn't
need it. Orion now scores each incoming message for complexity and routes
it to Claude Haiku (fast, cheap) or Sonnet (the default, stronger model)
accordingly, on by default (`ORION_MODEL_ROUTING_ENABLED=true` in
`.env.example`; set to `false` to always use Sonnet like before).

This is **cloud-only routing between two Claude tiers** — not a switch to
a local/offline model. Orion already has a genuinely local fallback for
when Claude is unreachable at all (§17, via Ollama); this is a separate,
unrelated feature that only ever calls Claude, just picking which size.

The scorer (`core/routing.py`) is a weighted heuristic — length, code/math
domain signals, reasoning/multi-step phrasing, question/subtask count, and
creative-writing signals, each contributing to a 0.0–1.0 complexity score —
directly adapted from [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)'s
own query-complexity router (`src/openjarvis/learning/routing/`), a Stanford
Hazy Research project. Two differences from their design: every pattern is
bilingual (French + English, matching how Orion is actually used) where
theirs is English-only, and since Orion only ever has two cloud tiers
instead of an open-ended local-model registry, the router is a binary
threshold rather than a model-registry search. The rules, in order:

1. **Code or math signals → Sonnet**, regardless of how short the message
   looks ("fix `x=1/0`" is four words but exactly the kind of message where
   a wrong-but-confident Haiku answer is worse than a slower Sonnet one).
2. **Low complexity score, no code/math → Haiku** ("hi", "what time is
   it", "merci").
3. **High complexity, multi-step phrasing, or explicit reasoning language
   → Sonnet** ("explain step by step why... then compare... 1. cost? 2.
   latency?").
4. **Everything else (the ambiguous middle) → Sonnet** — ties go to the
   model whose failure mode is "a bit slower," not "confidently wrong."

The model is picked once per turn from the user's message text, but a
reply that turns out to need several rounds of tool calls is doing more
work than a one-shot text classification could have predicted from the
first message alone — if a turn routed to Haiku is still asking for tools
after 3 rounds, Orion escalates to Sonnet for the rest of that turn rather
than riding Haiku's weaker judgement through an increasingly complex
tool-use chain.

## 20. MCP (connecting to external tool servers)

Orion can connect to external [MCP](https://modelcontextprotocol.io) (Model
Context Protocol) servers and use their tools alongside every hand-written
integration above — the same idea as OpenJarvis's `mcp_adapter.py`, adapted
to this project's own tool registry (`tools/registry_builder.py`) instead
of theirs.

Setup:

```bash
pip install -r requirements-mcp.txt
cp mcp_servers.example.json mcp_servers.json   # then edit it
```

Set `MCP_SERVERS_CONFIG_PATH=./mcp_servers.json` in `.env`. The file uses
the same `"mcpServers"` shape as Claude Desktop/Cursor/etc., so an existing
config from another MCP client usually works unchanged:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/me/Documents"]
    },
    "some-remote-server": { "url": "https://example.com/mcp" }
  }
}
```

Each entry is either a local subprocess speaking MCP over stdio (`command`
+ `args`, optionally `env`) or a remote server speaking MCP over
Streamable HTTP (`url`). On startup, Orion connects to every configured
server once, lists its tools, and registers each one into the same
registry every other tool lives in — Claude can call an MCP tool exactly
like `get_weather` or `send_gmail`, with no special-casing anywhere in
`core/agent.py`. Each connection stays open for the process's lifetime
(not reconnected per call) so a stateful server keeps its state between
turns, and closes cleanly on shutdown.

A server that's misconfigured or unreachable is logged and skipped —
never blocks the others, and never blocks the rest of Orion's own tools
from registering, matching every other optional integration in
`tools/registry_builder.py`. Leave `MCP_SERVERS_CONFIG_PATH` unset (the
default) to skip MCP entirely.

## 21. WhatsApp interface

Same idea as §6's Telegram interface — voice-in, voice-out, owner-only,
proactive reminders/health alerts — but through Meta's official WhatsApp
Cloud API instead of Telegram's bot API. Mirrors `interfaces/telegram_bot.py`'s
shape closely (`interfaces/whatsapp_bot.py`), with one structural difference:
WhatsApp is webhook-based (Meta pushes messages to a URL you register)
rather than polling, so this needs a real, internet-reachable HTTPS
endpoint in front of it — more setup than Telegram's "paste a token and
run it."

Setup:

1. Create a [Meta Developer app](https://developers.facebook.com/apps)
   with the WhatsApp product added, and a WhatsApp Business phone number
   (Meta provides a free test number for development). From the app
   dashboard: `WHATSAPP_ACCESS_TOKEN` (a temporary token works for testing;
   generate a permanent one via a System User for real use) and
   `WHATSAPP_PHONE_NUMBER_ID`.
2. Set `WHATSAPP_VERIFY_TOKEN` to any string you make up yourself, and
   `WHATSAPP_APP_SECRET` from the app's Basic Settings — this one isn't
   optional the way it might look: it's what proves an inbound webhook
   request actually came from Meta (see the security note below).
3. Set `WHATSAPP_ALLOWED_NUMBER` to your own WhatsApp number in E.164
   without the leading `+` (e.g. `41791234567`) — only messages from this
   number get answered.
4. Install the same dependencies the web HUD uses (FastAPI + uvicorn):
   `pip install -r requirements-web.txt`.
5. Run it: `python -m interfaces.whatsapp_bot` — listens locally on
   `WHATSAPP_WEBHOOK_PORT` (default 8422).
6. Expose that port to the internet over HTTPS — a reverse proxy (nginx +
   Let's Encrypt) if this runs on a server with a domain, or a tunnel
   (ngrok, Cloudflare Tunnel) for development/testing. Meta requires HTTPS
   for the webhook URL; this project doesn't set that part up for you, same
   as §18's web HUD deliberately staying HTTP-only for local use.
7. In the Meta app dashboard, configure the webhook: URL =
   `https://<your-domain>/webhook`, verify token = whatever you put in
   `WHATSAPP_VERIFY_TOKEN`, subscribe to the `messages` field.
8. Message your WhatsApp Business number from your phone. Text in gets
   text back; a voice message in gets transcribed *and* answered with a
   spoken voice message back (plus the text), same as Telegram.

**Security note**: every inbound webhook POST is authenticated via the
`X-Hub-Signature-256` header (HMAC-SHA256 over the raw body, keyed by
`WHATSAPP_APP_SECRET`) before anything in it — including the sender's
number, which the owner-only check depends on — is trusted. Without this,
anyone who discovered the webhook URL could POST a fake message claiming
to be from your number and have Orion act on it. This check fails closed:
no `WHATSAPP_APP_SECRET` configured means every request is rejected, not
"verification skipped."

**Honest limitation**: the Cloud API only allows free-form,
business-initiated messages (reminders, health alerts) within the 24-hour
window after you last messaged Orion — outside that window, an unprompted
push needs a pre-approved message template, which this project doesn't set
up. In practice this means proactive pushes work as long as you talk to
Orion at least once a day; if you go quiet for longer, they log a failure
instead of crashing and resume as soon as you message Orion again
(reopening the window). Text/voice replies to something you sent are
unaffected either way — that limitation only applies to messages Orion
sends unprompted.

## What's deferred (from the full integration wishlist)

Some requested integrations aren't in yet, on purpose:

- **Video generation** (Veo or similar): no free tier and billed per
  second of output — see §14 for the actual numbers. Needs an explicit
  cost ceiling agreed on before it's wired up, not a default-on tool.
- **Microsoft 365 beyond Mail/Calendar/Contacts** (OneDrive, Teams): §15
  covers Outlook Mail/Calendar/Contacts, mirroring the Google integration's
  scope (§2) — OneDrive file access and Teams aren't built, ask if you want
  either added.
- **Autonomous crypto trade execution** (real exchange/broker API
  integration, no confirmation step): §12 covers what's actually built —
  research, comparison, technical indicators, and a paper portfolio with a
  mandatory human confirmation before any position changes. Wiring that up
  to a real exchange to place unsupervised orders is a materially
  different, much higher-stakes step this project doesn't take — see §12
  for the reasoning.
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

## Response speed — what to actually expect

Orion goes through Claude for every reply, which is fundamentally slower
than a search engine's precomputed index — no LLM is going to feel as
instant as Google for a query that needs the model to reason. What *is*
already done to close that gap as much as it can be:

- **Streaming**: replies are streamed sentence by sentence, so on the voice
  interfaces Orion starts speaking the first sentence as soon as it's
  ready, not after the whole answer is generated.
- **Prompt caching**: the (large) set of tool definitions and the static
  system prompt are cached, so they aren't reprocessed on every single
  turn — [Anthropic's own guidance](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
  puts the latency reduction from this at up to 85% for long, mostly-static
  prompts, which the tool list here is.
- **Lookup caching**: read-only lookups (weather, web search, dictionary,
  currency conversion, ...) are cached in memory per process, each for as
  long as that kind of answer stays valid (`core/tool_cache.py` — minutes
  for weather/news, up to a day for things like dictionary definitions or
  video transcripts that basically never change). Asking the same or a
  just-repeated question skips the tool *and* the extra Claude round trip
  it costs entirely. Financial/live-status tools (stock/crypto prices,
  uptime checks) are deliberately excluded — a cached answer there would
  be actively misleading, not just slightly stale.
- **Background consolidation**: once a session's history passes 60
  messages, an extra Claude call rewrites the running conversation summary
  (`core/consolidation.py`) — previously this ran inline, silently adding
  a whole second API round trip's worth of latency to whichever response
  happened to cross that threshold. It now runs in a background thread and
  uses `ORION_FAST_MODEL` (a Haiku model by default) instead of the main
  model, since a digest nobody reads directly doesn't need frontier-level
  reasoning.
- **Tighter output budget**: capped at 1024 tokens instead of 2048 —
  generation is sequential, so every output token adds directly to
  latency, and a fast conversational reply doesn't need 1500 words of
  headroom. A single turn that genuinely needs more (a long document via a
  tool call's arguments) just continues across tool-use iterations rather
  than needing one huge one.
- **Voice endpoint timing**: the trailing-silence window used to decide
  you've finished speaking dropped from 1.2s to 0.7s, now that it's backed
  by real ambient-noise calibration instead of a fixed threshold that
  needed the extra margin to avoid false cutoffs in a noisy room.
- **Parallel tool calls, capped**: when a single turn needs several
  independent tools (e.g. weather and a crypto price), they used to run one
  after another, paying every tool's latency in sequence. `core/agent.py`
  dispatches a turn's tool calls concurrently (a thread pool), so the turn
  only costs as long as its slowest tool — not their sum. Capped at
  `MAX_CONCURRENT_TOOL_CALLS` (8): a turn that happens to reach for a large
  batch of tools at once opens at most that many threads/outbound requests
  in one burst, rather than one per tool — more tools in a turn than that
  is more likely to trip a provider's rate limit than to finish faster,
  since most of them are I/O-bound on the same handful of external APIs.
- **Pooled HTTP connections**: every tool that calls an external API (~20
  files, Shopify/Microsoft Graph/CoinGecko/GitHub/weather/... — everything
  except `core/offline_agent.py`'s local Ollama calls) used to go through
  httpx's module-level `httpx.get`/`httpx.post`/etc., which by design opens
  a brand new connection — a full TCP handshake, then a TLS handshake for
  every `https://` call — and tears it down again after each single
  request. They now share one persistent `httpx.Client` (`core/http.py`),
  so a repeat call to a host already used this session (Shopify's API
  during one longer store-management conversation, say) reuses an existing
  connection instead of paying that handshake again. Registered with
  `atexit` to close cleanly on shutdown rather than just being left for the
  OS to reclaim.
- **Telegram replies no longer block reminders/health alerts**: the bot's
  reply generation, voice transcription, and TTS encoding are blocking
  calls, often several seconds long — running them directly inside an
  `async def` handler used to freeze the bot's single event loop for that
  whole duration, which also stalls `JobQueue` (the same loop delivers
  reminders and health alerts) and further incoming messages. They now run
  via `asyncio.to_thread`, so the loop stays free to keep polling and firing
  scheduled jobs while a reply is being generated.

## Reliability

**Full tool-by-tool correctness review.** Beyond the cross-cutting fixes
below, every tool in `tools/` (~150 across ~65 files) was read end to end
looking for business-logic bugs specific to each one, not just the shared
patterns above. Highlights, each with a regression test:

- **`emergency_wipe` didn't wipe everything it claimed to**: behavioral
  corrections, crypto holdings/proposals, and saved quant signals were
  left behind after a "wipe all local history" call — now included.
- **Path traversal in generated-document/video filenames**: `document_name`
  (docx/pptx/xlsx create tools) and `format` (video conversion) were used
  unsanitized to build a filename — a value like `../../../../tmp/evil`
  could write outside `outputs/`. Both are now confined to it.
- **Outlook event creation silently forced UTC**: Microsoft Graph's
  `dateTime` field is a naive local-time string paired with a separate
  timezone name, not an embedded offset the way Google Calendar's API
  works — a bare local time used to land several hours off from what was
  meant. Now requires and correctly converts a real UTC offset.
- **Gmail `read_email` silently truncated to a snippet**: body extraction
  only scanned one level of MIME parts, so any message with an attachment
  (nested `multipart/mixed` → `multipart/alternative` → `text/plain`)
  fell back to Gmail's ~100-char preview with no indication the "full
  body" wasn't actually full. Now recurses.
- **Shopify sales summary silently truncated at 250 orders** (Shopify's
  page size, no pagination) and **summed mixed currencies as one number**;
  **`fulfill_order` reported full success while only fulfilling the first
  of several open fulfillment orders** on a split order. All three fixed.
- **Spreadsheet tools always wrote to the first sheet**, ignoring one
  added via `add_spreadsheet_sheet` — silently landing content on the
  wrong tab. All four row/formula/chart/format tools now take an optional
  `sheet_name`. Formatting a cell's color also used to reset its bold/
  size/name to defaults instead of merging — fixed to merge.
- **`read_word_document` dropped table content entirely** (only walks
  top-level paragraphs) — now included.
- **`audit_code_security` could silently drop a real HIGH-severity
  finding**: bandit's results are ordered by scan position, not severity,
  and the 30-result cap used to apply before sorting — a false negative in
  a tool whose whole purpose is surfacing real issues. Now sorts by
  severity first and notes when results are truncated.
- **`get_lyrics` broke on any artist/title containing `/`** (unescaped
  into the URL path, e.g. "AC/DC"), **`convert_currency` reported a valid
  same-currency conversion as failed** (the API omits a trivial 1:1 rate
  from its response), **`get_crypto_price` crashed with a raw KeyError**
  for an unsupported `vs_currency`, **`get_historical_weather` crashed
  outright when run on Feb 29** comparing against a non-leap year, and
  **`add_project_milestone` rejected its own documented example**
  ('2 weeks' — the duration parser had no week unit). All fixed.

- **A crypto trade can't be double-applied by a concurrent confirm/reject**:
  `core/store.py`'s `confirm_crypto_trade`/`reject_crypto_trade` used to
  read a proposal's status, then separately apply it to holdings and write
  the new status — two calls for the same proposal id at once (`core/agent.py`
  dispatches a turn's tool calls concurrently) could both read 'pending'
  before either wrote, silently doubling the position. Fixed two layers
  deep: the status is now claimed with a single atomic
  `UPDATE ... WHERE status = 'pending'` before anything else runs, *and*
  the whole method body is now guarded by a lock, because a raw
  `sqlite3.Connection`'s `check_same_thread=False` only disables Python's
  same-thread assertion — it doesn't make one connection object safe to
  drive from multiple threads truly concurrently for a multi-statement
  sequence, as a `tests/test_crypto_store.py` regression test firing ten
  concurrent confirms at the same proposal found the hard way (a handful of
  threads got through and doubled the holding, or the connection raised a
  low-level `sqlite3.DatabaseError` — reproduced consistently before the
  fix, gone after it, verified across repeated runs).
- **One bad TTS synthesis can't take down the always-on voice service**:
  `interfaces/voice/voice_loop.py`'s main `while True` loop had no
  exception handling around a conversation turn — same failure mode
  `ReminderScheduler`/`HealthMonitor` were already fixed against earlier,
  just not yet applied here. A single unexpected error (a TTS backend
  hiccup, anything else unforeseen) used to crash the whole process,
  silently ending wake-word listening until someone noticed the systemd
  service (§8) had died and restarted it. Now caught, logged, and the loop
  keeps listening. Related: `core/tts.py`'s Edge TTS backend decodes its
  mp3 response via an `ffmpeg` subprocess call that — unlike every other
  subprocess call in this codebase — had no timeout; a truncated/corrupted
  stream (a network hiccup mid-response) could hang it indefinitely. Both
  now bounded. (voice_loop.py can't be imported in this project's own dev/CI
  sandbox — `sounddevice` needs a real PortAudio install this environment
  doesn't have — so this specific fix is verified by inspection rather than
  an automated test, unlike everything else in this section; the ffmpeg
  timeout half of it does have one, in `tests/test_tts.py`.)
- **Concurrent requests to the same session can't corrupt the conversation**:
  the web UI (§18) lets two browser tabs share one conversation by design.
  Since FastAPI runs each request in a thread pool, two `/api/chat` calls
  hitting the same session at once (two tabs, or a rapid double-send) used
  to be able to race `Agent.respond_streaming`'s read-history/append-message
  sequence against each other — worst case, two consecutive "user" turns
  land with no assistant reply between them, which the Messages API's
  strict role-alternation rejects outright. A per-session lock now rejects
  the second request cleanly (a toast: "Orion is still answering the
  previous message") instead of letting them interleave.
- **No duplicate background maintenance under rapid-fire messages**: every
  reply spawns a background thread to check whether conversation history or
  corrections need consolidating (§ below and "How Orion learns"). A burst
  of quick successive messages used to be able to spawn several of these at
  once, racing to consolidate the same overflow and paying for the same
  Claude call twice. A non-blocking lock now caps it at one maintenance run
  in flight at a time; a turn that finds one already running just skips its
  own; the next turn's check covers the same ground.
- **Tool result cache can't grow unbounded**: `core/tool_cache.py`'s
  in-memory cache used to only ever evict the *one* key it was asked for —
  an entry for a query that's never repeated (a one-off `web_search`, say)
  would sit in memory forever once expired. Every 200 writes it now sweeps
  everything already expired in one pass, so memory stays bounded by live
  entries, not all-time-ever-cached ones — matters over a long-running
  process with heavy, varied lookup traffic.
- **`outputs/` can't grow forever unnoticed**: every generated file (images,
  documents, videos, ...) landed under `outputs/` and nothing ever removed
  an old one. Off by default — auto-deleting a user's files without being
  asked isn't something this project does unprompted — but setting
  `ORION_OUTPUTS_RETENTION_DAYS` opts into an automatic sweep at each
  interface's startup (`core/outputs_cleanup.py`), and the `clean_old_outputs`
  tool covers an explicit one-off cleanup either way. `outputs/websites/` is
  never touched by either path — those are live, redeployable site
  projects (§13), not disposable generated one-offs.
- **Semantic memory search doesn't re-fetch everything from disk on every
  call**: `core/vector_memory.py`'s `search()` used to re-query every row
  from SQLite and re-decode each embedding's raw bytes from scratch on
  every single call, even for two searches back to back with nothing newly
  indexed in between. Rows are now cached in memory after the first search
  and kept in sync by appending in `index()`, instead of re-querying —
  matters most for corrections (§ "How Orion learns") and notes/documents
  indexed into semantic memory over a long-running session.
- **A hung SQL query can't freeze `run_sql_query` indefinitely**: a missing
  `WHERE`/`LIMIT` (or a genuinely stuck connection) used to be able to hang
  the tool call — and by extension that turn — for as long as the query
  took, with no way back short of killing the process. It now runs on a
  daemon thread with a `timeout_seconds` cap (default 30s): the tool call
  fails fast with a clear message past that point rather than hanging.
  There's no portable, dialect-safe way to actually cancel an in-flight
  query from another thread, so the query itself may keep running against
  the database in the background — but Orion is no longer stuck waiting on
  it.

- **WAL mode on every SQLite store**: `core/memory.py`, `core/store.py`,
  and `core/vector_memory.py` share one `orion.db` file across several
  connections, hit from several threads at once (the scheduler, the health
  monitor, background consolidation, and now concurrent tool dispatch
  above). The default rollback-journal mode locks the whole file per
  writer; WAL lets a writer and readers proceed together instead, with
  `busy_timeout` making real contention wait and retry rather than
  immediately erroring with "database is locked".
- **Background loops survive a bad poll**: `ReminderScheduler` and
  `HealthMonitor` each run their own always-on thread. Previously, the one
  call that actually reads from the store (`due_reminders()` /
  `pending_alerts()`) wasn't wrapped in a try/except — a single transient
  error there (lock contention, a disk hiccup) would kill that thread
  permanently, silently ending reminders or health alerts for the rest of
  the process's life with no signal to the user. Both loops now catch and
  log that failure and keep polling, the same way a failed *notification*
  was already handled.
- **Persistent logging**: every interface now calls
  `core/logging_setup.py`'s `configure_logging()` at startup, which adds a
  rotating log file (`ORION_LOG_PATH`, default `./orion.log`, ~5MB × 4
  files kept) alongside the existing console output. Diagnosing a headless
  or backgrounded run (§8, a systemd service, a Task Scheduler job) no
  longer depends on a terminal that's since closed.

The single biggest remaining cost is **tool calls**: the *first* time a
question needs live information (weather, web search, "what's the news
today"), it costs a second full round trip to Claude — one call decides to
use the tool, the tool runs, a second call turns the result into an answer
— on top of however long the tool itself takes. Lookup caching (above)
removes that cost for a repeated or near-repeated question, but not for a
genuinely new one. `web_search` in particular scrapes
DuckDuckGo's HTML results (no API key needed, but also no speed guarantee)
rather than querying a precomputed index the way Google does, so "any
information, as fast as Google" isn't fully achievable for anything
requiring a live lookup — that's an inherent gap between an agent that
reasons about what to look up and a search engine that already has it
indexed, not something prompt engineering fixes.

Published reference numbers (not from this project, from
[public 2026 API benchmarks](https://www.kunalganglani.com/blog/llm-api-latency-benchmarks-2026)):
Claude Haiku 4.5 delivers its first token in ~0.4-0.6s; Sonnet models are
in the ~0.9-1.2s range. `ORION_MODEL` defaults to Sonnet for capability —
switching it to a Haiku model would measurably cut latency at some cost to
answer quality, if that trade is ever worth making for this use case.

`scripts/benchmark_latency.py` measures your actual setup once you have a
real `ANTHROPIC_API_KEY` in `.env` (this project's own dev environment has
none, so these numbers can't be produced here) — time to first sentence
and total time, for a plain question, a question needing a tool call, and
back-to-back questions in one session to see prompt caching's effect:

```bash
python -m scripts.benchmark_latency
```

## Privacy notes

- Only your Anthropic API calls leave the device by default; STT/TTS for
  the voice interface run entirely locally (Whisper + Piper).
- The Telegram bot only responds to `TELEGRAM_ALLOWED_USER_ID` — anyone
  else's messages are silently ignored.
- All memory (conversation history, remembered facts) lives in a local
  SQLite file (`ORION_DB_PATH`) — nothing is synced anywhere.

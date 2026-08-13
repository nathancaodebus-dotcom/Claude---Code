(() => {
  "use strict";

  const coreHeroEl = document.getElementById("core-hero");
  const coreMiniEl = document.getElementById("core-mini");
  const heroHintEl = document.getElementById("hero-hint");
  const inputEl = document.getElementById("input");
  const sendEl = document.getElementById("send");
  const micEl = document.getElementById("mic");
  const notificationsEl = document.getElementById("notifications");
  const clockEl = document.getElementById("readout-clock");
  const coreReadoutEl = document.getElementById("readout-core");
  const modelReadoutEl = document.getElementById("readout-model");
  const statusLineEl = document.getElementById("status-line");
  const brandNameEl = document.getElementById("brand-name");

  // --- clock ---

  function tickClock() {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString("fr-FR", { hour12: false });
  }
  tickClock();
  setInterval(tickClock, 1000);

  // --- status ---

  fetch("/api/status")
    .then((r) => r.json())
    .then((data) => {
      brandNameEl.textContent = (data.assistant_name || "ORION").toUpperCase();
      modelReadoutEl.textContent = data.model || "--";
      coreReadoutEl.textContent = data.ready ? "OK" : "NO KEY";
      if (!data.ready) {
        statusLineEl.textContent = "ANTHROPIC_API_KEY MISSING";
      }
    })
    .catch(() => {
      coreReadoutEl.textContent = "OFFLINE";
      statusLineEl.textContent = "BACKEND UNREACHABLE";
    });

  // --- state (idle / thinking / speaking) driving the core emblem + equalizer ---

  function setState(state) {
    for (const el of [coreHeroEl, coreMiniEl]) {
      el.classList.remove("state-thinking", "state-speaking");
      if (state) el.classList.add(`state-${state}`);
    }
    visualizer.setMode(state || "idle");
  }

  // --- particles: a slow drifting ring of dots inside the hero emblem ---

  function initParticles() {
    const canvas = document.getElementById("particles");
    const ctx = canvas.getContext("2d");
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const count = 70;
    // Icy blue/violet/teal, matching the constellation-nebula palette —
    // varied per particle so the drift reads as a starfield, not one flat color.
    const hues = [
      "rgba(215, 226, 255, 0.7)",
      "rgba(124, 147, 255, 0.6)",
      "rgba(155, 107, 255, 0.5)",
      "rgba(33, 201, 184, 0.45)",
    ];
    const particles = Array.from({ length: count }, () => {
      const angle = Math.random() * Math.PI * 2;
      const radius = 90 + Math.random() * 70;
      return {
        angle,
        radius,
        speed: (Math.random() - 0.5) * 0.006,
        wobble: Math.random() * Math.PI * 2,
        size: Math.random() * 1.6 + 0.4,
        hue: hues[Math.floor(Math.random() * hues.length)],
      };
    });

    function frame() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const p of particles) {
        p.angle += p.speed;
        p.wobble += 0.02;
        const r = p.radius + Math.sin(p.wobble) * 6;
        const x = cx + Math.cos(p.angle) * r;
        const y = cy + Math.sin(p.angle) * r;
        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = p.hue;
        ctx.fill();
      }
      requestAnimationFrame(frame);
    }
    frame();
  }
  initParticles();

  // --- equalizer: a ring of radial bars around the circle that reacts
  // while Orion is thinking/replying, standing in for a visible transcript
  // (per the user's request: keep the input bar, lose the written
  // back-and-forth). The bar levels themselves are still synthetic —
  // randomly re-targeted and eased every frame, the same trick a lot of
  // "audio reactive" UIs use when there's no waveform to read — but real
  // speech audio now plays alongside it (see the audio queue below), so
  // the animation reads as reacting to Orion's actual voice rather than
  // being pure decoration. ---

  const visualizer = (() => {
    const canvas = document.getElementById("visualizer");
    const ctx = canvas.getContext("2d");
    const BAR_COUNT = 72;
    const bars = Array.from({ length: BAR_COUNT }, () => ({ level: 0, target: 0 }));
    let mode = "idle";
    let lastKick = 0;

    function kick(intensity, coverage) {
      for (const bar of bars) {
        if (Math.random() < coverage) {
          bar.target = Math.random() * intensity;
        }
      }
    }

    function setMode(next) {
      mode = next;
      if (mode === "idle") {
        for (const bar of bars) bar.target = 0.04 + Math.random() * 0.03;
      }
    }

    function lerpChannel(a, b, t) {
      return Math.round(a + (b - a) * Math.min(1, Math.max(0, t)));
    }

    function barColor(i, level) {
      // Sweep teal -> icy blue -> violet across the ring, matching the
      // nebula palette; brighter/more opaque the higher the level.
      const t = i / BAR_COUNT;
      const stops = [
        [33, 201, 184],
        [124, 147, 255],
        [155, 107, 255],
      ];
      const segment = t * (stops.length - 1);
      const idx = Math.min(stops.length - 2, Math.floor(segment));
      const localT = segment - idx;
      const [r1, g1, b1] = stops[idx];
      const [r2, g2, b2] = stops[idx + 1];
      const r = lerpChannel(r1, r2, localT);
      const g = lerpChannel(g1, g2, localT);
      const b = lerpChannel(b1, b2, localT);
      const alpha = 0.3 + level * 0.6;
      return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
    }

    function frame(ts) {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (w > 0 && h > 0 && (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr))) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      if (w > 0 && h > 0) {
        const cx = w / 2;
        const cy = h / 2;
        const innerR = Math.min(w, h) * 0.335;
        const maxBarLen = Math.min(w, h) * 0.13;

        if (mode === "speaking" && ts - lastKick > 90) {
          kick(1, 0.65);
          lastKick = ts;
        } else if (mode === "thinking" && ts - lastKick > 220) {
          kick(0.4, 0.4);
          lastKick = ts;
        }

        for (let i = 0; i < BAR_COUNT; i++) {
          const bar = bars[i];
          bar.level += (bar.target - bar.level) * 0.18;
          const angle = (i / BAR_COUNT) * Math.PI * 2 - Math.PI / 2;
          const len = 3 + bar.level * maxBarLen;
          const x1 = cx + Math.cos(angle) * innerR;
          const y1 = cy + Math.sin(angle) * innerR;
          const x2 = cx + Math.cos(angle) * (innerR + len);
          const y2 = cy + Math.sin(angle) * (innerR + len);

          ctx.strokeStyle = barColor(i, bar.level);
          ctx.lineWidth = 2.2;
          ctx.lineCap = "round";
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();
        }
      }

      requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
    return { setMode };
  })();

  // --- notifications: proactive pushes (reminders/alerts), errors, and
  // generated attachments all surface here as brief toasts — this is
  // deliberately the *only* visible record of what Orion says or does,
  // no scrolling transcript. ---

  function showNotification(text, { isError = false } = {}) {
    const el = document.createElement("div");
    el.className = isError ? "notification error" : "notification";
    el.textContent = text;
    notificationsEl.appendChild(el);
    setTimeout(() => el.remove(), 12000);
    return el;
  }

  function showAttachments(paths) {
    for (const path of paths || []) {
      const el = document.createElement("div");
      el.className = "notification";
      if (/\.(png|jpe?g|gif|webp|svg)$/i.test(path)) {
        const img = document.createElement("img");
        img.className = "attachment-thumb";
        img.src = `/${path}`;
        img.alt = path;
        el.appendChild(img);
      } else {
        const link = document.createElement("a");
        link.className = "attachment-link";
        link.href = `/${path}`;
        link.textContent = `📎 ${path.split("/").pop()}`;
        link.target = "_blank";
        link.rel = "noopener";
        el.appendChild(link);
      }
      notificationsEl.appendChild(el);
      setTimeout(() => el.remove(), 20000);
    }
  }

  // --- spoken replies: each "sentence" SSE event carries a base64 WAV
  // (synthesized server-side by the same TTS backends Telegram/the voice
  // loop use — core/tts.py) alongside its text. Queued and played one at a
  // time in order, since sentences can arrive faster than they take to
  // speak. audio is null when no TTS backend is configured (§18/§7) —
  // the equalizer-only animation is what that degrades to. ---

  const audioQueue = [];
  const audioPlayer = new Audio();
  let audioPlaying = false;

  function playNextQueuedAudio() {
    const next = audioQueue.shift();
    if (!next) {
      audioPlaying = false;
      return;
    }
    audioPlaying = true;
    audioPlayer.src = next;
    // Autoplay can be blocked if the browser no longer considers this
    // triggered by the user gesture that started sendMessage() (rare, but
    // possible on a slow reply) — fail quietly into silent mode rather
    // than throwing an unhandled rejection; the equalizer still animates.
    audioPlayer.play().catch(() => {});
  }
  audioPlayer.addEventListener("ended", playNextQueuedAudio);

  function enqueueSpokenSentence(base64Wav) {
    if (!base64Wav) return;
    audioQueue.push(`data:audio/wav;base64,${base64Wav}`);
    if (!audioPlaying) playNextQueuedAudio();
  }

  function resetAudioQueue() {
    audioQueue.length = 0;
    audioPlayer.pause();
    audioPlayer.removeAttribute("src");
    audioPlaying = false;
  }

  // --- sending a message, streaming the SSE reply into the equalizer only ---

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = "";
    inputEl.disabled = true;
    sendEl.disabled = true;

    setState("thinking");
    heroHintEl.textContent = "PROCESSING…";
    resetAudioQueue();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));

          if (event.type === "sentence") {
            setState("speaking");
            enqueueSpokenSentence(event.audio);
          } else if (event.type === "done") {
            showAttachments(event.attachments);
          } else if (event.type === "error") {
            showNotification(event.text || "Une erreur est survenue.", { isError: true });
          }
        }
      }
    } catch (err) {
      showNotification(`Connexion perdue avec le backend (${err}).`, { isError: true });
    } finally {
      setState(null);
      heroHintEl.textContent = "WAITING FOR COMMAND";
      inputEl.disabled = false;
      sendEl.disabled = false;
      inputEl.focus();
    }
  }

  sendEl.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });
  inputEl.focus();

  // --- mic input: click once to start, then just talk — recording stops
  // itself once you go quiet (same idea as interfaces/voice/voice_loop.py's
  // silence detection, reimplemented here in the Web Audio API since
  // there's no way to reuse that server-side Python against a live browser
  // mic stream). Not always-listening like the Raspberry Pi voice loop
  // (a browser tab can't keep a mic open unattended with a wake word) —
  // still needs the initial click, just not a second one to end it. A
  // manual click while recording still stops it early as a fallback/
  // override. Clip goes to /api/transcribe (faster-whisper server-side,
  // same model the Pi/Telegram use) and the resulting text is sent
  // exactly like typing it in would be. ---

  const SILENCE_CALIBRATION_MS = 400; // brief ambient-level sample before judging silence, mirrors voice_loop.py's calibration
  const SILENCE_MARGIN_MULTIPLIER = 2.5; // threshold = ambient RMS * this
  const MIN_SILENCE_RMS = 0.015; // floor, in case the room is closer to silent than any mic's noise floor
  // 2s, not the 1.2s this started at: a longer sentence has ordinary
  // thinking/breathing pauses *inside* it that are longer than 1.2s, and
  // those used to get misread as "done talking," cutting the recording
  // off mid-sentence. 2s is closer to how long a real listener waits
  // before assuming someone's finished, at some cost to how snappy the
  // auto-stop feels on short utterances.
  const TRAILING_SILENCE_MS = 2000;
  const MAX_INITIAL_SILENCE_MS = 6000; // give up if nothing is said at all
  // 2 minutes: not a normal constraint, a safety net for if silence
  // detection itself somehow never fires (e.g. a very noisy room) --
  // without this, that failure mode records forever instead of eventually
  // giving up and letting the turn fail cleanly.
  const MAX_RECORDING_MS = 120000;

  let audioContext = null;
  let silenceCheckInterval = null;

  function computeRms(analyser, buffer) {
    analyser.getByteTimeDomainData(buffer);
    let sumSquares = 0;
    for (let i = 0; i < buffer.length; i++) {
      const normalized = (buffer[i] - 128) / 128;
      sumSquares += normalized * normalized;
    }
    return Math.sqrt(sumSquares / buffer.length);
  }

  function startSilenceDetection(stream) {
    const AudioContextCls = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCls) return; // no Web Audio API here -- degrades to manual click-to-stop only

    audioContext = new AudioContextCls();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    const buffer = new Uint8Array(analyser.fftSize);

    const calibrationSamples = [];
    const calibrationStart = Date.now();
    const recordingStart = calibrationStart;
    let silenceThreshold = MIN_SILENCE_RMS;
    let calibrated = false;
    let speechDetected = false;
    let silenceStart = null;

    silenceCheckInterval = setInterval(() => {
      const rms = computeRms(analyser, buffer);
      const now = Date.now();

      if (!calibrated) {
        calibrationSamples.push(rms);
        if (now - calibrationStart >= SILENCE_CALIBRATION_MS) {
          const ambient = calibrationSamples.reduce((a, b) => a + b, 0) / calibrationSamples.length;
          silenceThreshold = Math.max(MIN_SILENCE_RMS, ambient * SILENCE_MARGIN_MULTIPLIER);
          calibrated = true;
        }
        return;
      }

      if (rms > silenceThreshold) {
        speechDetected = true;
        silenceStart = null;
      } else {
        if (silenceStart === null) silenceStart = now;
        const limit = speechDetected ? TRAILING_SILENCE_MS : MAX_INITIAL_SILENCE_MS;
        if (now - silenceStart > limit) {
          stopRecording();
          return;
        }
      }

      if (now - recordingStart > MAX_RECORDING_MS) stopRecording();
    }, 100);
  }

  function stopSilenceDetection() {
    if (silenceCheckInterval) {
      clearInterval(silenceCheckInterval);
      silenceCheckInterval = null;
    }
    if (audioContext) {
      audioContext.close().catch(() => {});
      audioContext = null;
    }
  }

  let mediaRecorder = null;
  let recordedChunks = [];
  // True for the entire click-to-permission-prompt-resolves window, not
  // just while mediaRecorder is live — mediaRecorder stays null until
  // getUserMedia() resolves, so without this a second click during that
  // (very real, e.g. the user clicking again while the browser's own
  // permission popup is still up) fell through to a second concurrent
  // startRecording() call, racing to overwrite mediaRecorder with two
  // separate streams instead of being treated as "already starting."
  let micBusy = false;

  // A full spoken back-and-forth (multiple turns without re-clicking the
  // mic each time), not one-shot push-to-talk: click starts the session,
  // each utterance auto-stops on silence and gets transcribed+sent+
  // answered, then the mic reopens on its own for the next turn -- until
  // the user clicks again to end it, or MAX_CONSECUTIVE_FAILURES worth of
  // back-to-back failed turns ends it automatically rather than silently
  // hammering the transcription endpoint forever on something that's
  // consistently broken (e.g. faster-whisper genuinely not installed).
  const MAX_CONSECUTIVE_FAILURES = 3;
  let conversationActive = false;
  let consecutiveFailures = 0;

  function endConversation(reason) {
    conversationActive = false;
    consecutiveFailures = 0;
    if (reason) showNotification(reason, { isError: true });
    if (mediaRecorder && mediaRecorder.state === "recording") stopRecording();
  }

  const micSupported =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function" &&
    typeof window.MediaRecorder !== "undefined";

  if (!micSupported) {
    // Most likely causes, in order: not localhost/127.0.0.1 over plain
    // HTTP (getUserMedia needs a secure context — see README §18), a very
    // old/unusual browser, or a WebView that doesn't expose these APIs.
    // Disabling instead of leaving a button that fails silently on click.
    micEl.disabled = true;
    micEl.title = "Micro indisponible dans ce navigateur (getUserMedia manquant — voir README §18)";
  }

  async function startRecording() {
    if (micBusy) return;
    micBusy = true;

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      // err.name is the actionable part (NotAllowedError = permission
      // denied at the browser or, on Windows specifically, the OS-level
      // "Let desktop apps access your microphone" privacy toggle;
      // NotFoundError = no microphone device at all) — surfaced
      // explicitly rather than relying on the generic error string alone.
      const hint =
        err && err.name === "NotAllowedError"
          ? " Vérifie la permission micro du navigateur ET, sur Windows, Paramètres > Confidentialité > Microphone."
          : "";
      showNotification(`Micro inaccessible (${err}).${hint}`, { isError: true });
      micBusy = false;
      conversationActive = false; // nothing to retry here without fixing mic access itself
      return;
    }

    recordedChunks = [];
    try {
      mediaRecorder = new MediaRecorder(stream);
    } catch (err) {
      stream.getTracks().forEach((track) => track.stop());
      showNotification(`Impossible de démarrer l'enregistrement (${err}).`, { isError: true });
      micBusy = false;
      return;
    }
    mediaRecorder.addEventListener("dataavailable", (e) => {
      if (e.data.size > 0) recordedChunks.push(e.data);
    });
    mediaRecorder.addEventListener("stop", () => {
      stopSilenceDetection();
      stream.getTracks().forEach((track) => track.stop());
      micEl.classList.remove("recording");
      micEl.textContent = "🎤";
      heroHintEl.textContent = "WAITING FOR COMMAND";
      micBusy = false;
      if (recordedChunks.length === 0) {
        showNotification("Rien n'a été enregistré — réessaie.", { isError: true });
        return;
      }
      const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      transcribeAndSend(blob);
    });
    mediaRecorder.addEventListener("error", (e) => {
      showNotification(`Erreur d'enregistrement (${e.error || e}).`, { isError: true });
    });

    mediaRecorder.start();
    micEl.classList.add("recording");
    micEl.textContent = "■"; // ■ — still clickable to stop early manually
    heroHintEl.textContent = "LISTENING…";
    startSilenceDetection(stream);
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
  }

  async function transcribeAndSend(blob) {
    setState("thinking");
    heroHintEl.textContent = "TRANSCRIBING…";
    inputEl.disabled = true;
    sendEl.disabled = true;
    micEl.disabled = true;
    let turnSucceeded = false;

    try {
      const formData = new FormData();
      formData.append("audio", blob, "clip.webm");
      const response = await fetch("/api/transcribe", { method: "POST", body: formData });

      if (!response.ok) {
        showNotification(`Le serveur a refusé la transcription (HTTP ${response.status}).`, { isError: true });
        return;
      }

      const data = await response.json();
      if (data.error) {
        showNotification(data.error, { isError: true });
        return;
      }
      // Defends against a malformed/unexpected response shape (missing
      // "text") turning into the literal string "undefined" getting sent
      // as a chat message -- setting an <input>'s .value to undefined
      // stringifies it, and that string is truthy, so sendMessage() would
      // otherwise happily send it.
      if (typeof data.text !== "string" || !data.text.trim()) {
        showNotification("Réponse de transcription inattendue — réessaie.", { isError: true });
        return;
      }
      inputEl.value = data.text;
      await sendMessage();
      turnSucceeded = true;
    } catch (err) {
      showNotification(`Transcription impossible (${err}).`, { isError: true });
    } finally {
      setState(null);
      heroHintEl.textContent = "WAITING FOR COMMAND";
      inputEl.disabled = false;
      sendEl.disabled = false;
      micEl.disabled = false;

      if (conversationActive) {
        if (turnSucceeded) {
          consecutiveFailures = 0;
          startRecording(); // next turn, no click needed
        } else {
          consecutiveFailures += 1;
          if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
            endConversation(
              `Conversation arrêtée après ${MAX_CONSECUTIVE_FAILURES} échecs consécutifs — clique sur le micro pour réessayer.`
            );
          } else {
            startRecording(); // give it another try before giving up on the session
          }
        }
      }
    }
  }

  if (micSupported) {
    micEl.addEventListener("click", () => {
      if (conversationActive) {
        // Ends the whole back-and-forth, not just the current utterance
        // -- if a recording is in progress it still finishes that turn
        // (transcribed and sent, same as any other stop), it just won't
        // reopen the mic afterward.
        endConversation();
      } else {
        conversationActive = true;
        consecutiveFailures = 0;
        startRecording();
      }
    });
  }

  // --- proactive notifications (reminders, health alerts) ---

  try {
    const events = new EventSource("/api/events");
    events.onmessage = (evt) => {
      const data = JSON.parse(evt.data);
      if (data.type === "notification") {
        showNotification(data.text);
      }
    };
  } catch (err) {
    // EventSource unsupported or blocked — notifications just won't be proactive; chat still works.
  }
})();

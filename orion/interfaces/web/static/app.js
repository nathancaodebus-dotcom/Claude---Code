(() => {
  "use strict";

  const coreHeroEl = document.getElementById("core-hero");
  const coreMiniEl = document.getElementById("core-mini");
  const heroHintEl = document.getElementById("hero-hint");
  const inputEl = document.getElementById("input");
  const sendEl = document.getElementById("send");
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

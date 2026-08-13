(() => {
  "use strict";

  const heroEl = document.getElementById("hero");
  const chatEl = document.getElementById("chat");
  const chatLogEl = document.getElementById("chat-log");
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

  let chatStarted = false;
  let orionMessageEl = null;

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

  // --- state (idle / thinking / speaking) driving the core emblem's animation speed ---

  function setState(state) {
    for (const el of [coreHeroEl, coreMiniEl]) {
      el.classList.remove("state-thinking", "state-speaking");
      if (state) el.classList.add(`state-${state}`);
    }
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

  // --- chat rendering ---

  function scrollToBottom() {
    chatLogEl.scrollTop = chatLogEl.scrollHeight;
  }

  function startChatIfNeeded() {
    if (chatStarted) return;
    chatStarted = true;
    heroEl.style.opacity = "0";
    heroEl.style.transform = "scale(0.92)";
    setTimeout(() => {
      heroEl.hidden = true;
      chatEl.hidden = false;
    }, 350);
  }

  function appendMessage(role, text) {
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    const label = document.createElement("span");
    label.className = "msg-label";
    label.textContent = role === "user" ? "VOUS" : role === "error" ? "ERREUR" : "ORION";
    const body = document.createElement("span");
    body.className = "msg-body";
    body.textContent = text;
    el.appendChild(label);
    el.appendChild(body);
    chatLogEl.appendChild(el);
    scrollToBottom();
    return el;
  }

  function appendAttachments(container, paths) {
    for (const path of paths || []) {
      const url = `/${path}`;
      if (/\.(png|jpe?g|gif|webp|svg)$/i.test(path)) {
        const img = document.createElement("img");
        img.className = "attachment";
        img.src = url;
        img.alt = path;
        container.appendChild(img);
      } else {
        const link = document.createElement("a");
        link.className = "attachment-link";
        link.href = url;
        link.textContent = `📎 ${path.split("/").pop()}`;
        link.target = "_blank";
        link.rel = "noopener";
        container.appendChild(link);
      }
    }
  }

  // --- sending a message, streaming the SSE reply ---

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = "";
    inputEl.disabled = true;
    sendEl.disabled = true;

    startChatIfNeeded();
    appendMessage("user", text);
    setState("thinking");
    heroHintEl.textContent = "PROCESSING…";

    let bodyEl = null;
    let bodyText = "";

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
            if (!bodyEl) {
              bodyEl = appendMessage("orion", "");
            }
            bodyText += (bodyText ? " " : "") + event.text;
            bodyEl.querySelector(".msg-body").textContent = bodyText;
            scrollToBottom();
          } else if (event.type === "done") {
            if (!bodyEl) {
              bodyEl = appendMessage("orion", event.text || "");
            }
            appendAttachments(bodyEl, event.attachments);
          } else if (event.type === "error") {
            appendMessage("error", event.text || "Une erreur est survenue.");
          }
        }
      }
    } catch (err) {
      appendMessage("error", `Connexion perdue avec le backend (${err}).`);
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

  function showNotification(text) {
    const el = document.createElement("div");
    el.className = "notification";
    el.textContent = text;
    notificationsEl.appendChild(el);
    setTimeout(() => el.remove(), 12000);
  }

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

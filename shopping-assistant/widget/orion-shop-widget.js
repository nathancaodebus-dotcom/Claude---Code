/**
 * Embeddable shopping assistant widget. One script tag, no build step, no
 * dependencies — matches the same "no framework, no CDN" philosophy Orion
 * uses for the websites it generates. Configure via data attributes on the
 * script tag itself:
 *
 *   <script src="https://your-backend.example.com/orion-shop-widget.js"
 *           data-backend-url="https://your-backend.example.com"
 *           data-store-name="Your Store"></script>
 *
 * The CSS file (orion-shop-widget.css) must be hosted alongside this
 * script and is loaded automatically from the same directory.
 */
(function () {
  "use strict";

  var scriptEl = document.currentScript;
  var backendUrl = (scriptEl.dataset.backendUrl || "").replace(/\/$/, "");
  var storeName = scriptEl.dataset.storeName || "Shop Assistant";

  if (!backendUrl) {
    console.error("[orion-shop-widget] Missing data-backend-url on the script tag — the widget can't start.");
    return;
  }

  var cssHref = new URL("orion-shop-widget.css", scriptEl.src).href;
  var link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = cssHref;
  document.head.appendChild(link);

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = String(str == null ? "" : str);
    return div.innerHTML;
  }

  function getSessionId() {
    var key = "orion_shop_session_id";
    var existing = window.localStorage.getItem(key);
    if (existing) return existing;
    var fresh = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
    window.localStorage.setItem(key, fresh);
    return fresh;
  }

  var sessionId = getSessionId();

  var root = document.createElement("div");
  root.id = "orion-shop-widget-root";
  root.innerHTML =
    '<div class="osw-panel" id="osw-panel">' +
    '  <div class="osw-header"><span>' + escapeHtml(storeName) + '</span>' +
    '    <button class="osw-close" id="osw-close" aria-label="Close">&times;</button></div>' +
    '  <div class="osw-messages" id="osw-messages"></div>' +
    '  <div class="osw-inputbar">' +
    '    <input id="osw-input" type="text" placeholder="Ask about a product..." autocomplete="off">' +
    '    <button id="osw-send">Send</button>' +
    "  </div>" +
    "</div>" +
    '<button class="osw-bubble" id="osw-bubble" aria-label="Open chat">&#128172;</button>';
  document.body.appendChild(root);

  var panel = document.getElementById("osw-panel");
  var messagesEl = document.getElementById("osw-messages");
  var input = document.getElementById("osw-input");
  var sendBtn = document.getElementById("osw-send");

  document.getElementById("osw-bubble").addEventListener("click", function () {
    panel.classList.add("osw-open");
    input.focus();
    if (!messagesEl.children.length) {
      addMessage("assistant", "Hi! Ask me about products, or tell me what you're looking for.");
    }
  });
  document.getElementById("osw-close").addEventListener("click", function () {
    panel.classList.remove("osw-open");
  });

  function addMessage(role, text) {
    var el = document.createElement("div");
    el.className = "osw-msg osw-" + role;
    el.textContent = text;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  function renderProducts(products) {
    if (!products || !products.length) return;
    var wrap = document.createElement("div");
    wrap.className = "osw-products";
    products.forEach(function (p) {
      var card = document.createElement("div");
      card.className = "osw-product-card";
      var firstAvailable = (p.variants || []).find(function (v) { return v.available; });
      card.innerHTML =
        '<img src="' + escapeHtml(p.image_url || "") + '" alt="' + escapeHtml(p.title) + '" loading="lazy">' +
        '<div class="osw-product-info">' +
        '  <div class="osw-product-title">' + escapeHtml(p.title) + "</div>" +
        '  <div class="osw-product-price">' + escapeHtml(p.price) + " " + escapeHtml(p.currency) + "</div>" +
        (firstAvailable
          ? '  <button class="osw-add-btn" data-variant-id="' + escapeHtml(firstAvailable.id) + '">Add to cart</button>'
          : '  <button class="osw-add-btn" disabled>Sold out</button>') +
        "</div>";
      wrap.appendChild(card);
    });
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    wrap.querySelectorAll(".osw-add-btn[data-variant-id]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        addToCart(btn.getAttribute("data-variant-id"), btn);
      });
    });
  }

  function addToCart(variantId, btn) {
    btn.disabled = true;
    btn.textContent = "Adding...";
    fetch(backendUrl + "/cart/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, variant_id: variantId, quantity: 1 }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        btn.textContent = "Added ✓";
        if (data.cart) {
          addMessage("assistant", "Added to cart. Total: " + data.cart.total_amount + " " + data.cart.currency);
        }
      })
      .catch(function () {
        btn.disabled = false;
        btn.textContent = "Add to cart";
      });
  }

  function sendMessage() {
    var text = input.value.trim();
    if (!text) return;
    addMessage("user", text);
    input.value = "";
    sendBtn.disabled = true;
    var typing = addMessage("assistant", "...");
    typing.classList.add("osw-typing");

    fetch(backendUrl + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed");
        return res.json();
      })
      .then(function (data) {
        typing.remove();
        addMessage("assistant", data.reply || "Sorry, I didn't catch that.");
        renderProducts(data.products);
      })
      .catch(function () {
        typing.remove();
        addMessage("assistant", "Sorry, something went wrong. Please try again.");
      })
      .finally(function () {
        sendBtn.disabled = false;
      });
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") sendMessage();
  });
})();

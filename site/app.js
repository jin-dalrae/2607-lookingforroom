const state = {
  data: null,
  tab: "to_apply",
  view: "matches",
  apiOnline: false,
};

const els = {
  list: document.getElementById("list"),
  stats: document.getElementById("stats"),
  apiPill: document.getElementById("api-pill"),
  messagePre: document.getElementById("message-pre"),
  toast: document.getElementById("toast"),
};

function toast(text, isError = false) {
  els.toast.textContent = text;
  els.toast.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    els.toast.className = "toast";
  }, 4200);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    return false;
  }
}

function apiBase() {
  const fromData = (state.data?.apiUrl || "").trim();
  if (fromData) return fromData.replace(/\/$/, "");
  if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
    return "http://localhost:8787";
  }
  return "";
}

async function checkApi() {
  const base = apiBase();
  if (!base) {
    state.apiOnline = false;
    return;
  }
  try {
    const res = await fetch(`${base}/api/health`, { method: "GET" });
    const json = await res.json();
    state.apiOnline = Boolean(json.ok);
  } catch (_) {
    state.apiOnline = false;
  }
}

function filteredListings() {
  const items = state.data?.listings || [];
  return items.filter((item) => {
    if (item.queueStatus !== state.tab) return false;
    if (state.view === "matches" && !item.isMatch) return false;
    return true;
  });
}

function statusLabel(item) {
  if (item.queueStatus === "to_apply") return ["To apply", "status-todo"];
  if (item.queueStatus === "applied") return ["Awaiting reply", "status-wait"];
  if (item.queueStatus === "replied") return ["Replied", "status-done"];
  return [item.appStatus || "Other", "status-done"];
}

function renderCard(item, index) {
  const [label, labelClass] = statusLabel(item);
  const price = item.price ? `$${item.price}/mo` : "N/A";
  const badge = item.isFacebook ? " 📘" : "";
  const tags = [];
  if (item.isMatch) tags.push('<span class="tag match">Match</span>');
  if (item.transitTag) tags.push(`<span class="tag transit">${esc(item.transitTag)}</span>`);
  if (item.moveInTag) tags.push(`<span class="tag">${esc(item.moveInTag)}</span>`);

  return `
    <article class="card" data-id="${esc(item.id)}">
      <div class="card-top">
        <span class="rank">${index}</span>
        <div style="flex:1">
          <h2>${esc(item.title)}${badge}</h2>
          <p class="meta">${esc(price)} · ${esc(item.neighborhood)}</p>
          <div class="tags">${tags.join("")}</div>
        </div>
        <span class="status ${labelClass}">${label}</span>
      </div>
      <div class="actions">
        <button class="btn btn-primary apply-btn" data-id="${esc(item.id)}">Apply</button>
        <a class="btn btn-secondary" href="${esc(item.url)}" target="_blank" rel="noopener">Open</a>
        ${item.queueStatus === "to_apply" ? `<button class="btn btn-secondary sent-btn" data-id="${esc(item.id)}">Mark sent</button>` : ""}
      </div>
    </article>`;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render() {
  const items = filteredListings();
  els.list.innerHTML = items.length
    ? items.map((item, i) => renderCard(item, i + 1)).join("")
    : '<p class="empty">Nothing in this tab. Try switching to Pool or run <code>python run.py</code>.</p>';

  const c = state.data?.counts || {};
  els.stats.textContent = `${c.toApply ?? 0} to apply · ${c.applied ?? 0} awaiting · ${c.replied ?? 0} replied · ${items.length} shown`;

  els.apiPill.textContent = state.apiOnline
    ? "API online — real Gmail drafts"
    : "API offline — compose fallback";
  els.apiPill.className = `api-pill${state.apiOnline ? "" : " offline"}`;
}

async function fallbackApply(item) {
  if (item.isFacebook) {
    const copied = await copyText(item.message);
    window.open(item.url, "_blank", "noopener,noreferrer");
    toast(copied ? "Message copied — paste in Facebook Messenger" : "Open listing and paste your message");
    return;
  }
  window.open(item.gmailComposeUrl, "_blank", "noopener,noreferrer");
  toast("Gmail compose opened — save as draft or send");
}

async function applyListing(id) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return;

  const base = apiBase();
  if (!base) {
    await fallbackApply(item);
    return;
  }

  const btn = document.querySelector(`.apply-btn[data-id="${CSS.escape(id)}"]`);
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`${base}/api/draft/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json();
    if (!json.ok) {
      if (json.fallback === "gmailComposeUrl") {
        await fallbackApply(item);
        return;
      }
      throw new Error(json.error || "Apply failed");
    }
    if (json.mode === "facebook") {
      const copied = await copyText(json.message || item.message);
      window.open(json.url || item.url, "_blank", "noopener,noreferrer");
      toast(copied ? "Message copied — paste in Messenger" : "Open listing and paste message");
    } else {
      toast("Gmail draft saved — open Gmail → Drafts, then Mark sent");
    }
  } catch (err) {
    toast(String(err.message || err), true);
    await fallbackApply(item);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function markSent(id) {
  const base = apiBase();
  if (!base) {
    toast("Start api.py locally to sync status", true);
    return;
  }
  try {
    const res = await fetch(`${base}/api/sent/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "Failed");
    const item = (state.data?.listings || []).find((row) => row.id === id);
    if (item) {
      item.queueStatus = "applied";
      item.appStatus = "sent";
    }
    render();
    toast("Marked as sent");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

function bindControls() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.tab = btn.dataset.tab;
      render();
    });
  });
  document.querySelectorAll(".filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.view = btn.dataset.view;
      render();
    });
  });
  els.list.addEventListener("click", (event) => {
    const applyBtn = event.target.closest(".apply-btn");
    if (applyBtn) {
      applyListing(applyBtn.dataset.id);
      return;
    }
    const sentBtn = event.target.closest(".sent-btn");
    if (sentBtn) markSent(sentBtn.dataset.id);
  });
}

async function init() {
  const res = await fetch("./data.json?ts=" + Date.now());
  state.data = await res.json();
  els.messagePre.textContent = state.data.messageTemplate || "";
  await checkApi();
  bindControls();
  render();
}

init().catch((err) => {
  els.list.innerHTML = `<p class="empty">Failed to load queue: ${esc(err.message)}</p>`;
});
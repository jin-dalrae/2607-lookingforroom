const state = {
  data: null,
  tab: "to_apply",
  search: "",
  source: "all",
  maxPrice: "",
  moveInOnly: false,
  likedOnly: false,
  sortKey: "score",
  sortDir: -1,
  apiOnline: false,
  apiHasLike: false,
};

const LIKED_STORAGE_KEY = "queue-liked-ids";

const els = {
  tbody: document.getElementById("queue-body"),
  table: document.getElementById("queue-table"),
  toast: document.getElementById("toast"),
  search: document.getElementById("filter-search"),
  status: document.getElementById("filter-status"),
  source: document.getElementById("filter-source"),
  maxPrice: document.getElementById("filter-price"),
  moveInOnly: document.getElementById("filter-move-in"),
  likedOnly: document.getElementById("filter-liked"),
  rowCount: document.getElementById("row-count"),
  apiHint: document.getElementById("api-hint"),
  generatedHint: document.getElementById("generated-hint"),
  statToApply: document.getElementById("stat-to-apply"),
  statApplied: document.getElementById("stat-applied"),
  statReplied: document.getElementById("stat-replied"),
  statSkipped: document.getElementById("stat-skipped"),
};

function toast(text, isError = false) {
  els.toast.textContent = text;
  els.toast.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { els.toast.className = "toast"; }, 4200);
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
    state.apiHasSkip = false;
    state.apiHasLike = false;
    return;
  }
  try {
    const res = await fetch(`${base}/api/health`, { method: "GET" });
    const json = await res.json();
    state.apiOnline = Boolean(json.ok);
    const endpoints = Array.isArray(json.endpoints) ? json.endpoints : [];
    state.apiHasSkip = endpoints.includes("skip");
    state.apiHasLike = endpoints.includes("like");
  } catch (_) {
    state.apiOnline = false;
    state.apiHasSkip = false;
    state.apiHasLike = false;
  }
}

function loadLocalLikes() {
  try {
    const raw = localStorage.getItem(LIKED_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch (_) {
    return new Set();
  }
}

function saveLocalLikes(ids) {
  localStorage.setItem(LIKED_STORAGE_KEY, JSON.stringify([...ids]));
}

function mergeLocalLikes() {
  const local = loadLocalLikes();
  for (const item of state.data?.listings || []) {
    if (local.has(item.id)) item.liked = true;
  }
}

function parseTime(value) {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function statusMeta(item) {
  switch (item.queueStatus) {
    case "to_apply":
      return { label: "To apply", css: "apply" };
    case "applied":
      return { label: "Sent — awaiting reply", css: "sent" };
    case "replied":
      return { label: "Replied", css: "replied" };
    case "skipped":
      return { label: "Skipped", css: "skipped" };
    default:
      return { label: item.appStatus || "Other", css: "skipped" };
  }
}

function sourceLabel(item) {
  if (item.isFacebook) return "📘 Facebook";
  return "Craigslist";
}

function searchBlob(item) {
  return [
    item.title,
    item.neighborhood,
    item.rentalAddress,
    item.city,
    item.state,
    item.zip,
    item.transitTag,
    item.moveInTag,
    sourceLabel(item),
  ].filter(Boolean).join(" ").toLowerCase();
}

function passesFilters(item) {
  if (item.queueStatus !== state.tab) return false;
  if (state.moveInOnly && !item.isMatch) return false;
  if (state.likedOnly && !item.liked) return false;
  if (state.source === "facebook" && !item.isFacebook) return false;
  if (state.source === "craigslist" && item.isFacebook) return false;
  const maxPrice = state.maxPrice === "" ? null : Number(state.maxPrice);
  if (maxPrice !== null && Number.isFinite(maxPrice)) {
    const price = Number(item.price);
    if (!Number.isFinite(price) || price > maxPrice) return false;
  }
  const q = state.search.trim().toLowerCase();
  if (q && !searchBlob(item).includes(q)) return false;
  return true;
}

function sortValue(item, key) {
  switch (key) {
    case "price":
      return Number.isFinite(Number(item.price)) ? Number(item.price) : 99999;
    case "sqft":
      if (Number.isFinite(Number(item.sqft))) return Number(item.sqft);
      if (item.sizeTier === "large") return 200;
      return -1;
    case "liked":
      return item.liked ? 1 : 0;
    case "score":
      return Number.isFinite(Number(item.score)) ? Number(item.score) : -1;
    case "posted":
      return parseTime(item.postedAt) ?? 0;
    case "scraped":
      return parseTime(item.scrapedAt) ?? 0;
    case "neighborhood":
      return (item.neighborhood || "").toLowerCase();
    case "address":
      return (item.rentalAddress || "").toLowerCase();
    case "title":
      return (item.title || "").toLowerCase();
    case "status":
      return item.queueStatus || "";
    case "source":
      return item.source || "";
    default:
      return 0;
  }
}

function sortedFilteredItems() {
  const items = (state.data?.listings || []).filter(passesFilters);
  items.sort((a, b) => {
    const av = sortValue(a, state.sortKey);
    const bv = sortValue(b, state.sortKey);
    if (av < bv) return -1 * state.sortDir;
    if (av > bv) return 1 * state.sortDir;
    return (a.title || "").localeCompare(b.title || "");
  });
  return items;
}

function sqftCell(item) {
  if (Number.isFinite(Number(item.sqft))) {
    const n = Number(item.sqft);
    const cls = n < 100 ? "sqft-small" : item.meets150Sqft ? "sqft-good" : "";
    return `<span class="${cls}">${esc(String(n))}</span>`;
  }
  if (item.sqftLabel === "Large") {
    return '<span class="sqft-tier">Large</span>';
  }
  return "—";
}

function subLines(item) {
  const parts = [];
  if (item.isMatch) parts.push('<span class="tag-inline">Move-in OK</span>');
  if (item.transitTag) parts.push(`<span class="tag-inline">${esc(item.transitTag)}</span>`);
  if (item.moveInTag) parts.push(`<span class="tag-inline">${esc(item.moveInTag)}</span>`);
  return parts.length ? `<div class="cell-sub">${parts.join("")}</div>` : "";
}

function renderRow(item, index) {
  const st = statusMeta(item);
  const price = item.price ? `$${item.price}` : "—";
  const address = item.rentalAddress || "—";
  const posted = item.postedLabel || "—";
  const scraped = item.scrapedLabel || "—";
  const score = Number.isFinite(Number(item.score)) ? String(item.score) : "—";
  const rowClass = [
    "data-row",
    item.isMatch ? "match-row" : "",
    item.liked ? "liked-row" : "",
  ].filter(Boolean).join(" ");
  const search = esc(searchBlob(item));
  const starClass = item.liked ? "star-btn on" : "star-btn";

  const actionBtns = [
    `<button type="button" class="link-btn primary apply-btn" data-id="${esc(item.id)}">Apply</button>`,
    `<button type="button" class="link-btn toggle-detail" data-index="${index}">Message</button>`,
  ];
  if (item.queueStatus === "to_apply") {
    actionBtns.push(`<button type="button" class="link-btn sent-btn" data-id="${esc(item.id)}">Mark sent</button>`);
    actionBtns.push(`<button type="button" class="link-btn skip-btn" data-id="${esc(item.id)}">Skip</button>`);
  }

  const detailRow = `
    <tr class="detail-row" data-detail-for="${index}" hidden>
      <td colspan="13">
        <details class="message-box" open>
          <summary>Apply message</summary>
          <textarea rows="8" readonly>${esc(item.message || "")}</textarea>
        </details>
      </td>
    </tr>`;

  return `
    <tr class="${rowClass}"
        data-index="${index}"
        data-id="${esc(item.id)}"
        data-search="${search}"
        data-status="${esc(item.queueStatus)}"
        data-source="${esc(item.isFacebook ? "facebook" : "craigslist")}"
        data-neighborhood="${esc((item.neighborhood || "").toLowerCase())}"
        data-address="${esc((item.rentalAddress || "").toLowerCase())}"
        data-price="${sortValue(item, "price")}"
        data-sqft="${sortValue(item, "sqft")}"
        data-liked="${sortValue(item, "liked")}"
        data-score="${sortValue(item, "score")}"
        data-posted="${sortValue(item, "posted")}"
        data-scraped="${sortValue(item, "scraped")}"
        data-title="${esc((item.title || "").toLowerCase())}">
      <td class="num">${index}</td>
      <td class="star-cell">
        <button type="button" class="${starClass}" data-id="${esc(item.id)}" title="${item.liked ? "Unlike" : "Like"}">★</button>
      </td>
      <td class="title-cell">
        <a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a>
        ${subLines(item)}
      </td>
      <td class="num">${esc(price)}</td>
      <td class="num sqft-cell">${sqftCell(item)}</td>
      <td>${esc(item.neighborhood || "—")}</td>
      <td>${esc(address)}</td>
      <td>${esc(posted)}</td>
      <td>${esc(scraped)}</td>
      <td class="num">${esc(score)}</td>
      <td><span class="badge badge-${st.css}">${esc(st.label)}</span></td>
      <td><span class="badge badge-channel">${esc(sourceLabel(item))}</span></td>
      <td class="links-cell">${actionBtns.join("")}</td>
    </tr>
    ${detailRow}`;
}

function dataRows() {
  return Array.from(els.tbody.querySelectorAll("tr.data-row"));
}

function detailFor(index) {
  return els.tbody.querySelector(`tr.detail-row[data-detail-for="${index}"]`);
}

function updateSortHeaders() {
  els.table.querySelectorAll("thead th[data-sort]").forEach((th) => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.sort === state.sortKey) {
      th.classList.add(state.sortDir === 1 ? "sorted-asc" : "sorted-desc");
    }
  });
}

function render() {
  const items = sortedFilteredItems();
  els.tbody.innerHTML = items.length
    ? items.map((item, i) => renderRow(item, i + 1)).join("")
    : '<tr><td colspan="13" class="hint">Nothing here. Try another status or loosen filters.</td></tr>';

  const c = state.data?.counts || {};
  els.statToApply.textContent = String(c.toApply ?? 0);
  els.statApplied.textContent = String(c.applied ?? 0);
  els.statReplied.textContent = String(c.replied ?? 0);
  els.statSkipped.textContent = String(c.skipped ?? 0);
  els.rowCount.textContent = `${items.length} shown`;
  els.generatedHint.textContent = state.data?.generatedAt
    ? `Generated ${state.data.generatedAt}. Refresh: python listings_page.py`
    : "";
  els.apiHint.textContent = state.apiOnline
    ? state.apiHasSkip
      ? "API online on your Mac — Apply creates real Gmail drafts."
      : "API online but outdated — restart api.py so Skip works."
    : "API offline — Apply opens Gmail compose or copies Facebook message.";

  updateSortHeaders();
}

async function fallbackApply(item) {
  if (item.isFacebook) {
    const copied = await copyText(item.message);
    window.open(item.url, "_blank", "noopener,noreferrer");
    toast(copied ? "Message copied — paste in Messenger" : "Open listing and paste your message");
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

function setItemLiked(id, liked) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (item) item.liked = liked;
  const local = loadLocalLikes();
  if (liked) local.add(id);
  else local.delete(id);
  saveLocalLikes(local);
}

async function toggleLike(id) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return;
  const next = !item.liked;
  const base = apiBase();

  if (!base || !state.apiHasLike) {
    setItemLiked(id, next);
    render();
    toast(next ? "Liked (saved in this browser)" : "Unliked");
    return;
  }

  try {
    const res = await fetch(`${base}/api/like/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ liked: next }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) throw new Error(json.error || "Failed");
    setItemLiked(id, Boolean(json.liked));
    const local = loadLocalLikes();
    local.delete(id);
    saveLocalLikes(local);
    render();
    toast(json.liked ? "Liked" : "Unliked");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

async function markSkipped(id) {
  const base = apiBase();
  if (!base) {
    toast("Start api.py locally to sync skip status", true);
    return;
  }
  if (!state.apiHasSkip) {
    toast("Restart api.py — your running copy is missing /api/skip", true);
    return;
  }
  try {
    const res = await fetch(`${base}/api/skip/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 404 && json.error === "Not found") {
        throw new Error("Restart api.py — skip endpoint not loaded");
      }
      throw new Error(json.error || "Failed");
    }
    if (!json.ok) throw new Error(json.error || "Failed");
    const item = (state.data?.listings || []).find((row) => row.id === id);
    if (item) {
      item.queueStatus = "skipped";
      item.appStatus = "skipped";
    }
    if (state.data?.counts) {
      state.data.counts.toApply = Math.max(0, (state.data.counts.toApply || 0) - 1);
      state.data.counts.skipped = (state.data.counts.skipped || 0) + 1;
    }
    render();
    toast("Skipped");
  } catch (err) {
    toast(String(err.message || err), true);
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
    if (state.data?.counts) {
      state.data.counts.toApply = Math.max(0, (state.data.counts.toApply || 0) - 1);
      state.data.counts.applied = (state.data.counts.applied || 0) + 1;
    }
    render();
    toast("Marked as sent");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

function bindControls() {
  const rerender = () => render();

  els.search.addEventListener("input", () => {
    state.search = els.search.value;
    rerender();
  });
  els.status.addEventListener("change", () => {
    state.tab = els.status.value;
    rerender();
  });
  els.source.addEventListener("change", () => {
    state.source = els.source.value;
    rerender();
  });
  els.maxPrice.addEventListener("input", () => {
    state.maxPrice = els.maxPrice.value;
    rerender();
  });
  els.moveInOnly.addEventListener("change", () => {
    state.moveInOnly = els.moveInOnly.checked;
    rerender();
  });
  els.likedOnly.addEventListener("change", () => {
    state.likedOnly = els.likedOnly.checked;
    rerender();
  });

  els.table.querySelectorAll("thead th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortDir *= -1;
      else {
        state.sortKey = key;
        state.sortDir = key === "title" || key === "neighborhood" || key === "address" ? 1 : -1;
      }
      rerender();
    });
  });

  els.tbody.addEventListener("click", (event) => {
    const starBtn = event.target.closest(".star-btn");
    if (starBtn) {
      toggleLike(starBtn.dataset.id);
      return;
    }
    const applyBtn = event.target.closest(".apply-btn");
    if (applyBtn) {
      applyListing(applyBtn.dataset.id);
      return;
    }
    const sentBtn = event.target.closest(".sent-btn");
    if (sentBtn) {
      markSent(sentBtn.dataset.id);
      return;
    }
    const skipBtn = event.target.closest(".skip-btn");
    if (skipBtn) {
      markSkipped(skipBtn.dataset.id);
      return;
    }
    const toggleBtn = event.target.closest(".toggle-detail");
    if (toggleBtn) {
      const detail = detailFor(toggleBtn.dataset.index);
      if (detail) detail.hidden = !detail.hidden;
    }
  });
}

async function init() {
  const res = await fetch("./data.json?ts=" + Date.now());
  state.data = await res.json();
  mergeLocalLikes();
  await checkApi();
  bindControls();
  render();
}

init().catch((err) => {
  els.tbody.innerHTML = `<tr><td colspan="13" class="hint">Failed to load queue: ${esc(err.message)}</td></tr>`;
});
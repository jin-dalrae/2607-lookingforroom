const state = {
  data: null,
  tab: "to_apply",
  search: "",
  source: "all",
  maxPrice: "",

  likedOnly: false,
  sortKey: "score",
  sortDir: -1,
  apiOnline: false,
  apiHasLike: false,
  apiHasDelete: false,
  apiHasReplied: false,
  lastClickedId: null,
  page: 1,
};

const PAGE_SIZE = 10;

const LIKED_STORAGE_KEY = "queue-liked-ids";
const SKIPPED_STORAGE_KEY = "queue-skipped-ids";
const DELETED_STORAGE_KEY = "queue-deleted-ids";
const LAST_CLICKED_KEY = "queue-last-clicked-id";
const DETAILS_PREVIEW_WORDS = 5;
const MOVE_IN_SORT_UNKNOWN = 999_999_999;

const MONTH_NUMBERS = {
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3,
  apr: 4, april: 4, may: 5, jun: 6, june: 6, jul: 7, july: 7,
  aug: 8, august: 8, sep: 9, sept: 9, september: 9, oct: 10, october: 10,
  nov: 11, november: 11, dec: 12, december: 12,
};

const els = {
  tbody: document.getElementById("queue-body"),
  table: document.getElementById("queue-table"),
  toast: document.getElementById("toast"),
  search: document.getElementById("filter-search"),
  status: document.getElementById("filter-status"),
  source: document.getElementById("filter-source"),
  maxPrice: document.getElementById("filter-price"),

  likedOnly: document.getElementById("filter-liked"),
  rowCount: document.getElementById("row-count"),
  apiHint: document.getElementById("api-hint"),
  generatedHint: document.getElementById("generated-hint"),
  statToApply: document.getElementById("stat-to-apply"),
  statApplied: document.getElementById("stat-applied"),
  statReplied: document.getElementById("stat-replied"),
  statSkipped: document.getElementById("stat-skipped"),
  statGone: document.getElementById("stat-gone"),
  pagination: document.getElementById("pagination"),
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
    state.apiHasDelete = false;
    state.apiHasReplied = false;
    return;
  }
  try {
    const res = await fetch(`${base}/api/health`, { method: "GET" });
    const json = await res.json();
    state.apiOnline = Boolean(json.ok);
    const endpoints = Array.isArray(json.endpoints) ? json.endpoints : [];
    state.apiHasSkip = endpoints.includes("skip");
    state.apiHasLike = endpoints.includes("like");
    state.apiHasDelete = endpoints.includes("delete");
    state.apiHasReplied = endpoints.includes("replied");
  } catch (_) {
    state.apiOnline = false;
    state.apiHasSkip = false;
    state.apiHasLike = false;
    state.apiHasDelete = false;
    state.apiHasReplied = false;
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

function loadLocalSkips() {
  try {
    const raw = localStorage.getItem(SKIPPED_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch (_) {
    return new Set();
  }
}

function saveLocalSkips(ids) {
  localStorage.setItem(SKIPPED_STORAGE_KEY, JSON.stringify([...ids]));
}

function queueStatusFromApp(appStatus) {
  if (!appStatus || appStatus === "draft") return "to_apply";
  if (appStatus === "skipped") return "skipped";
  if (appStatus === "replied") return "replied";
  if (appStatus === "rejected") return "gone";
  if (appStatus === "sent" || appStatus === "toured") return "applied";
  return "other";
}

function applyApplicationStatus(id, appStatus) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return false;
  item.appStatus = appStatus;
  item.queueStatus = queueStatusFromApp(appStatus);
  return true;
}

function recalculateCounts() {
  if (!state.data?.listings) return;
  const counts = {
    toApply: 0,
    applied: 0,
    replied: 0,
    skipped: 0,
    gone: 0,
    total: state.data.listings.length,
  };
  for (const item of state.data.listings) {
    if (item.queueStatus === "to_apply") counts.toApply += 1;
    else if (item.queueStatus === "applied") counts.applied += 1;
    else if (item.queueStatus === "replied") counts.replied += 1;
    else if (item.queueStatus === "skipped") counts.skipped += 1;
    else if (item.queueStatus === "gone") counts.gone += 1;
  }
  state.data.counts = { ...state.data.counts, ...counts };
}

async function syncApplicationStatuses() {
  const base = apiBase();
  if (!base || !state.apiOnline) return;
  try {
    const res = await fetch(`${base}/api/statuses`);
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok || !json.statuses) return;
    for (const item of state.data?.listings || []) {
      const appStatus = json.statuses[item.id];
      if (appStatus) applyApplicationStatus(item.id, appStatus);
    }
    recalculateCounts();
  } catch (_) {
    /* keep exported snapshot */
  }
}

function mergeLocalSkips() {
  const local = loadLocalSkips();
  for (const item of state.data?.listings || []) {
    if (local.has(item.id) && item.queueStatus === "to_apply") {
      item.queueStatus = "skipped";
      item.appStatus = "skipped";
    }
  }
  recalculateCounts();
}

function applySkipToItem(id) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item || item.queueStatus === "skipped") return false;
  const wasToApply = item.queueStatus === "to_apply";
  item.queueStatus = "skipped";
  item.appStatus = "skipped";
  if (state.data?.counts && wasToApply) {
    state.data.counts.toApply = Math.max(0, (state.data.counts.toApply || 0) - 1);
    state.data.counts.skipped = (state.data.counts.skipped || 0) + 1;
  }
  return true;
}

function loadLocalDeletes() {
  try {
    const raw = localStorage.getItem(DELETED_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch (_) {
    return new Set();
  }
}

function saveLocalDeletes(ids) {
  localStorage.setItem(DELETED_STORAGE_KEY, JSON.stringify([...ids]));
}

function loadLastClickedId() {
  try {
    return sessionStorage.getItem(LAST_CLICKED_KEY) || null;
  } catch (_) {
    return null;
  }
}

function saveLastClickedId(id) {
  try {
    if (id) sessionStorage.setItem(LAST_CLICKED_KEY, id);
    else sessionStorage.removeItem(LAST_CLICKED_KEY);
  } catch (_) {
    /* ignore */
  }
}

function markLastClicked(id) {
  if (!id) return;
  state.lastClickedId = id;
  saveLastClickedId(id);
  highlightLastClickedRow({ scroll: true, pulse: true });
}

function highlightLastClickedRow({ scroll = false, pulse = false } = {}) {
  const clickedId = state.lastClickedId;
  els.tbody.querySelectorAll("tr.data-row").forEach((row) => {
    row.classList.toggle("last-clicked-row", Boolean(clickedId && row.dataset.id === clickedId));
  });
  if (!clickedId) return;
  const clicked = els.tbody.querySelector(`tr.data-row[data-id="${CSS.escape(clickedId)}"]`);
  if (!clicked) return;
  if (scroll) {
    clicked.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  if (pulse) {
    clicked.classList.remove("last-clicked-pulse");
    void clicked.offsetWidth;
    clicked.classList.add("last-clicked-pulse");
  }
}

function applyLocalDeletes() {
  const local = loadLocalDeletes();
  if (!local.size || !state.data?.listings) return;
  for (const item of state.data.listings) {
    if (local.has(item.id)) {
      item.appStatus = "rejected";
      item.queueStatus = "gone";
    }
  }
}

function parseTime(value) {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function localTodayYmd() {
  const d = new Date();
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}

function isImmediateMoveIn(label) {
  const cleaned = String(label || "").trim().toLowerCase().replace(/[!.:;]+$/, "");
  return cleaned === "available now"
    || /^available\s+(now|immediately|asap)$/.test(cleaned)
    || /^(move[- ]?in\s+ready|ready\s+(?:for\s+move[- ]?in|to\s+move)|immediate(?:ly)?|asap|a\.?s\.?a\.?p\.?)$/.test(cleaned);
}

function parseDisplayMonthDay(label) {
  const match = String(label || "").trim().match(
    /^(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?$/i,
  );
  if (!match) return null;
  const month = MONTH_NUMBERS[match[1].toLowerCase()];
  const day = Number(match[2]);
  if (!month || !day) return null;
  const year = inferMoveInYear(month, day, null);
  return year * 10000 + month * 100 + day;
}

function inferMoveInYear(month, day, explicitYear) {
  if (explicitYear != null) {
    return explicitYear < 100 ? 2000 + explicitYear : explicitYear;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const candidates = [];
  for (const year of [today.getFullYear() - 1, today.getFullYear(), today.getFullYear() + 1]) {
    const dt = new Date(year, month - 1, day);
    if (dt.getFullYear() === year && dt.getMonth() === month - 1 && dt.getDate() === day) {
      candidates.push(dt);
    }
  }
  if (!candidates.length) return today.getFullYear();
  return candidates.reduce((best, dt) => {
    const bestDiff = Math.abs(best.getTime() - today.getTime());
    const dtDiff = Math.abs(dt.getTime() - today.getTime());
    return dtDiff < bestDiff ? dt : best;
  }).getFullYear();
}

function parseMoveInLabel(label) {
  const cleaned = String(label || "").trim();
  if (!cleaned || cleaned === "—") return null;
  if (isImmediateMoveIn(cleaned)) return localTodayYmd();

  const display = parseDisplayMonthDay(cleaned);
  if (display != null) return display;

  const monthDay = cleaned.match(
    /\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b/i,
  );
  if (monthDay) {
    const month = MONTH_NUMBERS[monthDay[1].toLowerCase()];
    const day = Number(monthDay[2]);
    const explicitYear = monthDay[3] ? Number(monthDay[3]) : null;
    if (month && day) {
      const year = inferMoveInYear(month, day, explicitYear);
      return year * 10000 + month * 100 + day;
    }
  }

  const slash = cleaned.match(/\b(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?\b/);
  if (slash) {
    const month = Number(slash[1]);
    const day = Number(slash[2]);
    if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
      let explicitYear = slash[3] ? Number(slash[3]) : null;
      if (explicitYear != null && explicitYear < 100) explicitYear += 2000;
      const year = inferMoveInYear(month, day, explicitYear);
      return year * 10000 + month * 100 + day;
    }
  }

  return null;
}

function moveInSortKey(item) {
  const parsed = parseMoveInLabel(item?.moveInLabel);
  if (parsed != null) return parsed;
  const raw = Number(item?.moveInSort);
  if (Number.isFinite(raw) && raw > 0 && raw < MOVE_IN_SORT_UNKNOWN) return raw;
  return MOVE_IN_SORT_UNKNOWN;
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
    case "gone":
      return { label: "Gone / rejected", css: "gone" };
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
    item.displayAddress,
    item.rentalAddress,
    item.neighborhood,
    item.city,
    item.state,
    item.zip,
    item.transitTag,
    item.moveInLabel,
    item.posterName,
    item.details,
    sourceLabel(item),
  ].filter(Boolean).join(" ").toLowerCase();
}

function passesFilters(item) {
  if (item.queueStatus !== state.tab) return false;

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
      if (Number.isFinite(Number(item.sqftSort))) return Number(item.sqftSort);
      return -1;
    case "movein":
      return moveInSortKey(item);
    case "liked":
      return item.liked ? 1 : 0;
    case "score":
      return Number.isFinite(Number(item.score)) ? Number(item.score) : -1;
    case "posted":
      return parseTime(item.postedAt) ?? 0;
    case "scraped":
      return parseTime(item.scrapedAt) ?? 0;
    case "address":
      return addressCell(item).toLowerCase();
    case "title":
      return (item.title || "").toLowerCase();
    case "details":
      return (item.details || "").toLowerCase();
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

function totalPages(itemCount) {
  return Math.max(1, Math.ceil(itemCount / PAGE_SIZE));
}

function clampPage(page, itemCount) {
  return Math.min(Math.max(1, page), totalPages(itemCount));
}

function paginatedItems(items) {
  const total = totalPages(items.length);
  state.page = clampPage(state.page, items.length);
  const start = (state.page - 1) * PAGE_SIZE;
  return items.slice(start, start + PAGE_SIZE);
}

function paginationSequence(current, total) {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const pages = new Set([1, total, current, current - 1, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const out = [];
  let prev = 0;
  for (const p of sorted) {
    if (p - prev > 1) out.push("…");
    out.push(p);
    prev = p;
  }
  return out;
}

function renderPagination(itemCount) {
  if (!els.pagination) return;
  const total = totalPages(itemCount);
  state.page = clampPage(state.page, itemCount);
  if (total <= 1) {
    els.pagination.innerHTML = "";
    return;
  }

  const parts = [];
  if (state.page > 1) {
    parts.push(`<button type="button" class="page-btn" data-page="${state.page - 1}">Prev</button>`);
  }
  for (const token of paginationSequence(state.page, total)) {
    if (token === "…") {
      parts.push('<span class="page-ellipsis">…</span>');
      continue;
    }
    const cls = token === state.page ? "page-btn active" : "page-btn";
    parts.push(`<button type="button" class="${cls}" data-page="${token}">${token}</button>`);
  }
  if (state.page < total) {
    parts.push(`<button type="button" class="page-btn" data-page="${state.page + 1}">Next</button>`);
  }
  els.pagination.innerHTML = parts.join("");
}

function goToPage(page) {
  const items = sortedFilteredItems();
  state.page = clampPage(page, items.length);
  render();
}

function sqftCell(item) {
  return item.sqftLabel ? esc(item.sqftLabel) : "—";
}

function addressCell(item) {
  const addr = (item.displayAddress || item.rentalAddress || "").trim();
  return addr || "—";
}

function subLines(item) {
  const tags = [];
  if (item.posterName) tags.push(`<span class="tag-inline tag-poster">${esc(item.posterName)}</span>`);
  if (item.transitTag) tags.push(`<span class="tag-inline">${esc(item.transitTag)}</span>`);
  if (!tags.length) return "";
  return `<div class="cell-sub">${tags.join("")}</div>`;
}

function detailsWordCount(text) {
  return String(text || "").trim().split(/\s+/).filter(Boolean).length;
}

function detailsPreview(text) {
  const cleaned = String(text || "").trim();
  if (!cleaned) return "";
  const words = cleaned.split(/\s+/).filter(Boolean);
  if (words.length <= DETAILS_PREVIEW_WORDS) return cleaned;
  return `${words.slice(0, DETAILS_PREVIEW_WORDS).join(" ")}…`;
}

function listingById(id) {
  return (state.data?.listings || []).find((row) => row.id === id);
}

function detailsCell(item) {
  const full = (item.details || "").trim();
  if (!full) return "—";
  const preview = detailsPreview(full);
  const expandable = detailsWordCount(full) > DETAILS_PREVIEW_WORDS;
  if (!expandable) return `<div class="details-cell">${esc(full)}</div>`;
  return `<div class="details-cell expandable" data-id="${esc(item.id)}" title="Click for full details">${esc(preview)}</div>`;
}

function applyMessage(item) {
  const template = (state.data?.messageTemplate || "").trim();
  const url = (item?.url || "").trim();
  if (!template) return "";
  if (!url || template.includes(url)) return template;
  const blocks = template.split("\n\n");
  if (blocks.length >= 2) {
    return `${blocks[0]}\n\n${url}\n\n${blocks.slice(1).join("\n\n")}`;
  }
  return `${template}\n\n${url}`;
}

function gmailComposeUrl(item) {
  const subject = encodeURIComponent(state.data?.subject || "Room inquiry");
  const body = encodeURIComponent(applyMessage(item));
  const to = encodeURIComponent(item?.to || "");
  let url = `https://mail.google.com/mail/?view=cm&fs=1&su=${subject}&body=${body}`;
  if (item?.to) url += `&to=${to}`;
  return url;
}

function renderRow(item, index) {
  const st = statusMeta(item);
  const price = item.price ? `$${item.price}` : "—";
  const address = addressCell(item);
  const posted = item.postedLabel || "—";
  const scraped = item.scrapedLabel || "—";
  const moveIn = item.moveInLabel || "—";
  const score = Number.isFinite(Number(item.score)) ? String(item.score) : "—";
  const rowClass = [
    "data-row",
    item.isMatch ? "match-row" : "",
    item.liked ? "liked-row" : "",
    item.id === state.lastClickedId ? "last-clicked-row" : "",
  ].filter(Boolean).join(" ");
  const starClass = item.liked ? "star-btn on" : "star-btn";

  const actionBtns = [
    `<button type="button" class="link-btn primary apply-btn" data-id="${esc(item.id)}">Apply</button>`,
  ];
  if (item.queueStatus === "to_apply") {
    actionBtns.push(`<button type="button" class="link-btn sent-btn" data-id="${esc(item.id)}">Mark sent</button>`);
    actionBtns.push(`<button type="button" class="link-btn skip-btn" data-id="${esc(item.id)}">Skip</button>`);
    actionBtns.push(`<button type="button" class="link-btn danger delete-btn" data-id="${esc(item.id)}">Delete</button>`);
  }
  if (item.queueStatus === "skipped") {
    actionBtns.push(`<button type="button" class="link-btn danger delete-btn" data-id="${esc(item.id)}">Delete</button>`);
  }
  if (item.queueStatus === "applied") {
    actionBtns.push(`<button type="button" class="link-btn replied-btn" data-id="${esc(item.id)}">Replied</button>`);
    actionBtns.push(`<button type="button" class="link-btn danger gone-btn" data-id="${esc(item.id)}">Gone</button>`);
  }
  if (item.queueStatus === "replied") {
    actionBtns.push(`<button type="button" class="link-btn danger gone-btn" data-id="${esc(item.id)}">Gone</button>`);
  }

  return `
    <tr class="${rowClass}"
        data-index="${index}"
        data-id="${esc(item.id)}">
      <td class="num">${index}</td>
      <td class="star-cell">
        <button type="button" class="${starClass}" data-id="${esc(item.id)}" title="${item.liked ? "Unlike" : "Like"}">★</button>
      </td>
      <td>${esc(address)}</td>
      <td class="title-cell">
        <a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a>
        ${subLines(item)}
      </td>
      <td class="details-col">${detailsCell(item)}</td>
      <td class="num">${esc(price)}</td>
      <td class="num sqft-cell">${sqftCell(item)}</td>
      <td>${esc(moveIn)}</td>
      <td>${esc(posted)}</td>
      <td>${esc(scraped)}</td>
      <td class="num">${esc(score)}</td>
      <td><span class="badge badge-${st.css}">${esc(st.label)}</span></td>
      <td><span class="badge badge-channel">${esc(sourceLabel(item))}</span></td>
      <td class="links-cell">${actionBtns.join("")}</td>
    </tr>`;
}

function dataRows() {
  return Array.from(els.tbody.querySelectorAll("tr.data-row"));
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
  const pageItems = paginatedItems(items);
  const startIndex = (state.page - 1) * PAGE_SIZE;
  els.tbody.innerHTML = items.length
    ? pageItems.map((item, i) => renderRow(item, startIndex + i + 1)).join("")
    : '<tr><td colspan="14" class="hint">Nothing here. Try another status or loosen filters.</td></tr>';

  const c = state.data?.counts || {};
  els.statToApply.textContent = String(c.toApply ?? 0);
  els.statApplied.textContent = String(c.applied ?? 0);
  els.statReplied.textContent = String(c.replied ?? 0);
  els.statSkipped.textContent = String(c.skipped ?? 0);
  if (els.statGone) els.statGone.textContent = String(c.gone ?? 0);
  const total = totalPages(items.length);
  els.rowCount.textContent = items.length
    ? `${pageItems.length} on page · ${items.length} total · page ${state.page}/${total}`
    : "0 shown";
  renderPagination(items.length);
  els.generatedHint.textContent = state.data?.generatedAt
    ? `Generated ${state.data.generatedAt}. Refresh: python listings_page.py`
    : "";
  els.apiHint.textContent = state.apiOnline
    ? state.apiHasSkip && state.apiHasReplied
      ? "API online — Mark sent / Replied / Gone sync to database."
      : "API online but outdated — restart api.py for full status sync."
    : "API offline — Apply still works; status buttons need api.py running locally.";

  updateSortHeaders();
  highlightLastClickedRow();
}

async function fallbackApply(item) {
  if (item.isFacebook) {
    const copied = await copyText(applyMessage(item));
    window.open(item.url, "_blank", "noopener,noreferrer");
    toast(copied ? "Message copied — paste in Messenger" : "Open listing and paste your message");
    return;
  }
  window.open(gmailComposeUrl(item), "_blank", "noopener,noreferrer");
  toast("Gmail compose opened — save as draft or send");
}

async function applyListing(id) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return;
  markLastClicked(id);
  await fallbackApply(item);
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

async function markGone(id, { label = "Gone" } = {}) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return;

  const base = apiBase();
  if (!base || !state.apiHasDelete) {
    const local = loadLocalDeletes();
    local.add(id);
    saveLocalDeletes(local);
    applyApplicationStatus(id, "rejected");
    recalculateCounts();
    render();
    toast(`${label} (saved in this browser)`);
    if (!base) return;
    if (!state.apiHasDelete) {
      toast("Restart api.py to sync status to database", true);
    }
    return;
  }

  try {
    const res = await fetch(`${base}/api/delete/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) throw new Error(json.error || "Failed");
    const local = loadLocalDeletes();
    local.delete(id);
    saveLocalDeletes(local);
    applyApplicationStatus(id, json.status || "rejected");
    recalculateCounts();
    render();
    toast(label);
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

async function deleteListing(id) {
  return markGone(id, { label: "Deleted" });
}

async function markSkipped(id) {
  const base = apiBase();

  if (!base || !state.apiHasSkip) {
    const local = loadLocalSkips();
    local.add(id);
    saveLocalSkips(local);
    if (applySkipToItem(id)) {
      render();
      toast("Skipped (saved in this browser)");
    }
    if (!base) return;
    if (!state.apiHasSkip) {
      toast("Restart api.py to sync skip to database", true);
    }
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
    const local = loadLocalSkips();
    local.delete(id);
    saveLocalSkips(local);
    applyApplicationStatus(id, json.status || "skipped");
    recalculateCounts();
    render();
    toast("Skipped");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

async function markReplied(id) {
  const base = apiBase();
  if (!base) {
    toast("Start api.py locally to sync status", true);
    return;
  }
  if (!state.apiHasReplied) {
    toast("Restart api.py — Replied endpoint not loaded", true);
    return;
  }
  try {
    const res = await fetch(`${base}/api/replied/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) throw new Error(json.error || "Failed");
    applyApplicationStatus(id, json.status || "replied");
    recalculateCounts();
    render();
    toast("Marked as replied");
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
    applyApplicationStatus(id, json.status || "sent");
    recalculateCounts();
    render();
    toast("Marked as sent");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

function bindControls() {
  const rerender = () => render();
  const rerenderFromStart = () => {
    state.page = 1;
    rerender();
  };

  els.search.addEventListener("input", () => {
    state.search = els.search.value;
    rerenderFromStart();
  });
  els.status.addEventListener("change", () => {
    state.tab = els.status.value;
    rerenderFromStart();
  });
  els.source.addEventListener("change", () => {
    state.source = els.source.value;
    rerenderFromStart();
  });
  els.maxPrice.addEventListener("input", () => {
    state.maxPrice = els.maxPrice.value;
    rerenderFromStart();
  });
  els.likedOnly.addEventListener("change", () => {
    state.likedOnly = els.likedOnly.checked;
    rerenderFromStart();
  });

  els.table.querySelectorAll("thead th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortDir *= -1;
      else {
        state.sortKey = key;
        state.sortDir = key === "title" || key === "address" || key === "movein" || key === "details" ? 1 : -1;
      }
      rerenderFromStart();
    });
  });

  els.pagination?.addEventListener("click", (event) => {
    const btn = event.target.closest(".page-btn");
    if (!btn?.dataset.page) return;
    goToPage(Number(btn.dataset.page));
  });

  els.tbody.addEventListener("click", (event) => {
    const detailsEl = event.target.closest(".details-cell.expandable");
    if (detailsEl) {
      const item = listingById(detailsEl.dataset.id);
      const full = (item?.details || "").trim();
      const preview = detailsPreview(full);
      const expanded = detailsEl.classList.toggle("expanded");
      detailsEl.textContent = expanded ? full : preview;
      return;
    }
    const titleLink = event.target.closest(".title-cell a");
    if (titleLink) {
      const row = titleLink.closest("tr.data-row");
      if (row?.dataset.id) markLastClicked(row.dataset.id);
      return;
    }
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
    const deleteBtn = event.target.closest(".delete-btn");
    if (deleteBtn) {
      deleteListing(deleteBtn.dataset.id);
      return;
    }
    const repliedBtn = event.target.closest(".replied-btn");
    if (repliedBtn) {
      markReplied(repliedBtn.dataset.id);
      return;
    }
    const goneBtn = event.target.closest(".gone-btn");
    if (goneBtn) {
      markGone(goneBtn.dataset.id);
      return;
    }
  });
}

async function init() {
  state.lastClickedId = loadLastClickedId();
  const res = await fetch("./data.json?ts=" + Date.now());
  state.data = await res.json();
  mergeLocalLikes();
  applyLocalDeletes();
  await checkApi();
  await syncApplicationStatuses();
  mergeLocalSkips();
  bindControls();
  render();
  if (state.lastClickedId) {
    highlightLastClickedRow({ scroll: true });
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && state.lastClickedId) {
      highlightLastClickedRow({ scroll: true, pulse: true });
    }
  });
}

init().catch((err) => {
  els.tbody.innerHTML = `<tr><td colspan="14" class="hint">Failed to load queue: ${esc(err.message)}</td></tr>`;
});
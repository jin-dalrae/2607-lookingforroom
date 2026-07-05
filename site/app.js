const state = {
  data: null,
  tab: "to_apply",
  search: "",
  source: "all",
  maxPrice: "",

  likedOnly: false,
  memoOnly: false,
  sortKey: "score",
  sortDir: -1,
  apiOnline: false,
  apiHasScrape: false,
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
const STATUS_CACHE_KEY = "queue-status-cache";
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
  memoOnly: document.getElementById("filter-memo"),
  rowCount: document.getElementById("row-count"),
  apiHint: document.getElementById("api-hint"),
  updatedHint: document.getElementById("updated-hint"),
  updatedSep: document.getElementById("updated-sep"),
  statToApply: document.getElementById("stat-to-apply"),
  statApplied: document.getElementById("stat-applied"),
  statReplied: document.getElementById("stat-replied"),
  statSkipped: document.getElementById("stat-skipped"),
  statGone: document.getElementById("stat-gone"),
  statPendingScore: document.getElementById("stat-pending-score"),
  statPendingScoreWrap: document.getElementById("stat-pending-score-wrap"),
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

function isLocalDev() {
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1";
}

function apiBase() {
  const fromData = (state.data?.apiUrl || "").trim();
  if (fromData) return fromData.replace(/\/$/, "");
  if (isLocalDev()) return "http://127.0.0.1:8787";
  return window.location.origin;
}

async function checkApi() {
  const base = apiBase();
  if (!base) {
    state.apiOnline = false;
    state.apiHasScrape = false;
    state.apiHasSkip = false;
    state.apiHasLike = false;
    state.apiHasDelete = false;
    state.apiHasReplied = false;
    return;
  }
  try {
    const res = await fetch(`${base}/api/health`, { method: "GET", credentials: "same-origin" });
    const json = await res.json();
    state.apiOnline = Boolean(json.ok);
    const endpoints = Array.isArray(json.endpoints) ? json.endpoints : [];
    state.apiHasScrape =
      Boolean(json.scrapeAvailable) ||
      endpoints.includes("scrape") ||
      endpoints.includes("scrape/status");
    state.apiHasSkip = endpoints.includes("skip");
    state.apiHasLike = endpoints.includes("like");
    state.apiHasDelete = endpoints.includes("delete");
    state.apiHasReplied = endpoints.includes("replied");
  } catch (_) {
    state.apiOnline = false;
    state.apiHasScrape = false;
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

function hasEverApplied(item) {
  if (item?.appSentAt) return true;
  const status = item?.appStatus;
  return status === "sent" || status === "toured" || status === "replied";
}

function hasEverReplied(item) {
  if (item?.appRepliedAt) return true;
  return item?.appStatus === "replied";
}

function hasEverSkipped(item) {
  if (item?.appSkippedAt) return true;
  return item?.appStatus === "skipped";
}

function hasEverGone(item) {
  if (item?.appRejectedAt) return true;
  return item?.appStatus === "rejected";
}

function queueStatusFromApp(appStatus) {
  if (!appStatus || appStatus === "draft") return "to_apply";
  if (appStatus === "skipped") return "skipped";
  if (appStatus === "replied") return "replied";
  if (appStatus === "rejected") return "gone";
  if (appStatus === "sent" || appStatus === "toured") return "applied";
  return "other";
}

function applyApplicationStatus(id, appStatus, isLocalAction = false) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return false;
  item.appStatus = appStatus;
  item.queueStatus = queueStatusFromApp(appStatus);
  if (isLocalAction) {
    const nowStr = new Date().toISOString();
    item.appUpdatedAt = nowStr;
    if (appStatus === "sent" && !item.appSentAt) item.appSentAt = nowStr;
    if (appStatus === "replied" && !item.appRepliedAt) item.appRepliedAt = nowStr;
    if (appStatus === "toured" && !item.appTouredAt) item.appTouredAt = nowStr;
    if (appStatus === "rejected" && !item.appRejectedAt) item.appRejectedAt = nowStr;
    if (appStatus === "skipped" && !item.appSkippedAt) item.appSkippedAt = nowStr;
  }
  return true;
}

function loadStatusCache() {
  try {
    const raw = localStorage.getItem(STATUS_CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_) {
    return {};
  }
}

function saveStatusCache(cache) {
  localStorage.setItem(STATUS_CACHE_KEY, JSON.stringify(cache));
}

function setCachedStatus(id, appStatus) {
  const cache = loadStatusCache();
  cache[id] = appStatus;
  saveStatusCache(cache);
}

function clearCachedStatus(id) {
  const cache = loadStatusCache();
  if (!(id in cache)) return;
  delete cache[id];
  saveStatusCache(cache);
}

function applyStatusCache() {
  const cache = loadStatusCache();
  for (const item of state.data?.listings || []) {
    const appStatus = cache[item.id];
    if (appStatus) applyApplicationStatus(item.id, appStatus);
  }
  recalculateCounts();
}

function mergeStatusCache(statuses) {
  const cache = loadStatusCache();
  for (const [id, appStatus] of Object.entries(statuses || {})) {
    if (appStatus) cache[id] = appStatus;
  }
  saveStatusCache(cache);
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
    if (hasEverApplied(item)) counts.applied += 1;
    if (hasEverReplied(item)) counts.replied += 1;
    if (hasEverSkipped(item)) counts.skipped += 1;
    if (hasEverGone(item)) counts.gone += 1;
    if (item.queueStatus === "to_apply") counts.toApply += 1;
  }
  state.data.counts = { ...state.data.counts, ...counts };
}

function applyServerLikes(likes) {
  if (!Array.isArray(likes)) return;
  const liked = new Set(likes);
  for (const item of state.data?.listings || []) {
    item.liked = liked.has(item.id);
  }
  saveLocalLikes(liked);
}

function applyServerNotes(notes) {
  if (!notes || typeof notes !== "object") return;
  for (const item of state.data?.listings || []) {
    if (notes[item.id]) item.notes = notes[item.id];
  }
}

function applyServerMilestones(milestones) {
  if (!milestones || typeof milestones !== "object") return;
  for (const item of state.data?.listings || []) {
    const m = milestones[item.id];
    if (!m) continue;
    if (m.sentAt) item.appSentAt = m.sentAt;
    if (m.repliedAt) item.appRepliedAt = m.repliedAt;
    if (m.touredAt) item.appTouredAt = m.touredAt;
    if (m.rejectedAt) item.appRejectedAt = m.rejectedAt;
    if (m.skippedAt) item.appSkippedAt = m.skippedAt;
    if (m.updatedAt) item.appUpdatedAt = m.updatedAt;
  }
}

async function syncApplicationStatuses() {
  const base = apiBase();
  const cache = loadStatusCache();
  if (!base || !state.apiOnline) return false;
  try {
    const res = await fetch(`${base}/api/statuses`, { credentials: "same-origin" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok || !json.statuses) return false;
    const statuses = json.statuses || {};
    for (const item of state.data?.listings || []) {
      const appStatus = statuses[item.id] || cache[item.id];
      if (appStatus) applyApplicationStatus(item.id, appStatus);
    }
    applyServerLikes(json.likes);
    applyServerNotes(json.notes);
    applyServerMilestones(json.milestones);
    mergeStatusCache(statuses);
    recalculateCounts();
    return true;
  } catch (_) {
    return false;
  }
}

function mergeLocalSkips() {
  const local = loadLocalSkips();
  for (const id of local) setCachedStatus(id, "skipped");
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
  if (!local.size) return;
  for (const id of local) setCachedStatus(id, "rejected");
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

function formatAppDate(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "";
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const m = months[d.getMonth()];
    const date = d.getDate();
    let hours = d.getHours();
    const ampm = hours >= 12 ? "PM" : "AM";
    hours = hours % 12;
    hours = hours ? hours : 12;
    const min = String(d.getMinutes()).padStart(2, "0");
    return `${m} ${date}, ${hours}:${min} ${ampm}`;
  } catch (_) {
    return "";
  }
}

function formatStatusDate(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "";
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${months[d.getMonth()]} ${d.getDate()}`;
  } catch (_) {
    return "";
  }
}

function statusCssFor(item) {
  switch (item.queueStatus) {
    case "to_apply":
      return "apply";
    case "applied":
      return item.appStatus === "toured" ? "toured" : "sent";
    case "replied":
      return "replied";
    case "skipped":
      return "skipped";
    case "gone":
      return "gone";
    default:
      return "skipped";
  }
}

function statusTimelineParts(item) {
  const parts = [];
  const add = (label, iso) => {
    const date = formatStatusDate(iso);
    if (date) parts.push(`${label} ${date}`);
  };
  if (item.appSentAt) add("Applied", item.appSentAt);
  if (item.appRepliedAt) add("Replied", item.appRepliedAt);
  if (item.appTouredAt) add("Visited", item.appTouredAt);
  if (item.appSkippedAt) add("Skipped", item.appSkippedAt);
  if (item.appRejectedAt) add("Gone", item.appRejectedAt);
  return parts;
}

function statusMeta(item) {
  const timeline = statusTimelineParts(item);
  if (timeline.length) {
    return {
      label: timeline.join(", "),
      css: statusCssFor(item),
      timeline: timeline.length > 1,
    };
  }

  const dateStr = item.appUpdatedAt ? formatStatusDate(item.appUpdatedAt) : "";
  const suffix = dateStr ? ` ${dateStr}` : "";

  switch (item.queueStatus) {
    case "to_apply":
      return { label: "To apply", css: "apply" };
    case "applied":
      return { label: "Applied" + suffix, css: "sent" };
    case "replied":
      return { label: "Replied" + suffix, css: "replied" };
    case "skipped":
      return { label: "Skipped" + suffix, css: "skipped" };
    case "gone":
      return { label: "Gone" + suffix, css: "gone" };
    default:
      return { label: (item.appStatus || "Other") + suffix, css: "skipped" };
  }
}

function sourceLabel(item) {
  if (item.isFacebook) return "📘 Facebook";
  return "Craigslist";
}

function isSearching() {
  return Boolean(state.search.trim());
}

function searchStatusRank(item) {
  if (item.queueStatus === "replied") return 0;
  if (item.appStatus === "toured") return 1;
  if (item.queueStatus === "to_apply") return 2;
  if (item.queueStatus === "applied") return 3;
  if (item.queueStatus === "skipped") return 4;
  if (item.queueStatus === "gone") return 5;
  return 6;
}

function searchBlob(item) {
  return [
    item.title,
    item.price ? String(item.price) : "",
    item.price ? "$" + item.price : "",
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
    item.notes,
    item.groupId ? "group-" + item.groupId : "",
    sourceLabel(item),
    statusTimelineParts(item).join(" "),
  ].filter(Boolean).join(" ").toLowerCase();
}

function passesFilters(item) {
  if (!isSearching() && state.tab !== "all" && item.queueStatus !== state.tab) return false;

  if (state.likedOnly && !item.liked) return false;
  if (state.memoOnly && !item.notes) return false;
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
      if (item.scorePending) return -2;
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
    if (isSearching()) {
      const rankDiff = searchStatusRank(a) - searchStatusRank(b);
      if (rankDiff !== 0) return rankDiff;
    }
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
  if (item.isGrouped) {
    tags.push(`<span class="tag-inline same-house-btn" data-group-id="${esc(item.groupId)}" style="background:#f3e8ff; color:var(--purple); padding:0.1rem 0.35rem; border-radius:4px; font-weight:700; cursor:pointer;" title="Click to show all listings for this house">🏠 Same House (${item.duplicateCount} other${item.duplicateCount > 1 ? "s" : ""})</span>`);
  }
  
  const tagsHtml = tags.length ? `<div class="cell-sub">${tags.join("")}</div>` : "";
  
  const memoText = item.notes || "";
  const memoHtml = `
    <div class="memo-wrap" style="margin-top:0.4rem; display:flex; align-items:center; gap:0.4rem;">
      <span style="font-size:0.75rem; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:0.02em;">Memo:</span>
      <input type="text" class="memo-input" data-id="${esc(item.id)}" value="${esc(memoText)}" placeholder="Add note / phone..." style="flex:1; font-size:0.8rem; padding:0.15rem 0.35rem; border:1px solid var(--border); border-radius:4px; max-width:16rem; background:#fafafa; color:var(--text);" autocomplete="off">
    </div>
  `;
  
  return tagsHtml + memoHtml;
}

function listingById(id) {
  return (state.data?.listings || []).find((row) => row.id === id);
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

function listingDetailsFull(item) {
  return ((item?.detailsRaw || item?.details) || "").trim();
}

function detailsCell(item) {
  const cleaned = (item.details || "").trim();
  const full = listingDetailsFull(item);
  if (!cleaned && !full) return "—";
  const preview = detailsPreview(cleaned || full);
  const expandable =
    detailsWordCount(full) > DETAILS_PREVIEW_WORDS ||
    full.length > (cleaned.length || 0) + 20;
  const pendingTag = item.detailsPending
    ? '<span class="details-pending-tag" title="Card summary — full post text still loading">Card</span> '
    : "";
  if (!expandable) {
    return `<div class="details-cell">${pendingTag}${esc(full)}</div>`;
  }
  return `<div class="details-cell expandable collapsed" data-id="${esc(item.id)}" title="Click for full details">${pendingTag}<span class="details-text">${esc(preview)}</span></div>`;
}

function renderDetailsCell(detailsEl, item, expanded) {
  const cleaned = (item?.details || "").trim();
  const full = listingDetailsFull(item);
  const preview = detailsPreview(cleaned || full);
  const pendingTag = item?.detailsPending
    ? '<span class="details-pending-tag" title="Card summary — full post text still loading">Card</span> '
    : "";
  const textEl = detailsEl.querySelector(".details-text");
  detailsEl.classList.toggle("expanded", expanded);
  detailsEl.classList.toggle("collapsed", !expanded);
  if (textEl) {
    textEl.textContent = expanded ? full : preview;
    return;
  }
  detailsEl.innerHTML = `${pendingTag}<span class="details-text">${esc(expanded ? full : preview)}</span>`;
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
  const score = item.scorePending
    ? '<span class="score-pending" title="Scoring not finished yet">Pending</span>'
    : Number.isFinite(Number(item.score))
      ? esc(String(item.score))
      : "—";
  const rowClass = [
    "data-row",
    item.isMatch ? "match-row" : "",
    item.liked ? "liked-row" : "",
    item.scorePending ? "pending-score-row" : "",
    item.id === state.lastClickedId ? "last-clicked-row" : "",
  ].filter(Boolean).join(" ");
  const starClass = item.liked ? "star-btn on" : "star-btn";

  const row1 = [];
  const row2 = [];

  if (item.queueStatus === "to_apply" || item.queueStatus === "skipped") {
    row1.push(`<button type="button" class="link-btn primary apply-btn" data-id="${esc(item.id)}">Apply</button>`);
  }
  if (item.queueStatus === "to_apply") {
    row1.push(`<button type="button" class="link-btn sent-btn" data-id="${esc(item.id)}">Sent</button>`);
    row1.push(`<button type="button" class="link-btn skip-btn" data-id="${esc(item.id)}">Skip</button>`);
    row2.push(`<button type="button" class="link-btn danger delete-btn" data-id="${esc(item.id)}">Delete</button>`);
    row2.push(`<button type="button" class="link-btn danger scam-btn" style="border-color:#ffccd5; background:#fff0f3; color:#d70015; margin:0;" data-id="${esc(item.id)}">Scam</button>`);
  }
  if (item.queueStatus === "skipped") {
    row2.push(`<button type="button" class="link-btn danger delete-btn" data-id="${esc(item.id)}">Delete</button>`);
    row2.push(`<button type="button" class="link-btn danger scam-btn" style="border-color:#ffccd5; background:#fff0f3; color:#d70015; margin:0;" data-id="${esc(item.id)}">Scam</button>`);
  }
  if (item.queueStatus === "applied") {
    row1.push(`<button type="button" class="link-btn replied-btn" data-id="${esc(item.id)}">Replied</button>`);
    row2.push(`<button type="button" class="link-btn danger gone-btn" data-id="${esc(item.id)}">Gone</button>`);
    row2.push(`<button type="button" class="link-btn danger delete-btn" data-id="${esc(item.id)}">Delete</button>`);
    row2.push(`<button type="button" class="link-btn danger scam-btn" style="border-color:#ffccd5; background:#fff0f3; color:#d70015; margin:0;" data-id="${esc(item.id)}">Scam</button>`);
  }
  if (item.queueStatus === "replied") {
    row1.push(`<button type="button" class="link-btn visited-btn" data-id="${esc(item.id)}">Visited</button>`);
    row2.push(`<button type="button" class="link-btn danger gone-btn" data-id="${esc(item.id)}">Gone</button>`);
    row2.push(`<button type="button" class="link-btn danger delete-btn" data-id="${esc(item.id)}">Delete</button>`);
    row2.push(`<button type="button" class="link-btn danger scam-btn" style="border-color:#ffccd5; background:#fff0f3; color:#d70015; margin:0;" data-id="${esc(item.id)}">Scam</button>`);
  }
  if (item.queueStatus === "gone") {
    row1.push(`<button type="button" class="link-btn revert-btn" data-id="${esc(item.id)}">Revert</button>`);
  }

  const row1Html = row1.length ? `<div class="action-row" style="display:flex; gap:0.35rem; margin-bottom:0.35rem;">${row1.join("")}</div>` : "";
  const row2Html = row2.length ? `<div class="action-row" style="display:flex; gap:0.35rem;">${row2.join("")}</div>` : "";
  const actionsHtml = `<div style="display:flex; flex-direction:column; align-items:flex-start;">${row1Html}${row2Html}</div>`;

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
      <td class="num score-cell">${score}</td>
      <td>${st.timeline
    ? `<span class="status-timeline status-timeline-${st.css}">${esc(st.label)}</span>`
    : `<span class="badge badge-${st.css}">${esc(st.label)}</span>`}</td>
      <td><span class="badge badge-channel">${esc(sourceLabel(item))}</span></td>
      <td class="links-cell">${actionsHtml}</td>
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
  const pendingScore = c.pendingScore ?? 0;
  if (els.statPendingScore) els.statPendingScore.textContent = String(pendingScore);
  if (els.statPendingScoreWrap) els.statPendingScoreWrap.hidden = pendingScore === 0;
  const total = totalPages(items.length);
  els.rowCount.textContent = items.length
    ? `${pageItems.length} on page · ${items.length} total · page ${state.page}/${total}`
    : "0 shown";
  renderPagination(items.length);
  const updatedAt = (state.data?.generatedAt || "").trim();
  if (els.updatedHint) {
    els.updatedHint.textContent = updatedAt ? `Updated ${updatedAt}` : "";
    els.updatedHint.hidden = !updatedAt;
  }
  if (els.updatedSep) els.updatedSep.hidden = !updatedAt;
  if (els.apiHint) {
    let apiMessage = "";
    if (!state.apiOnline) {
      apiMessage = isLocalDev()
        ? "Status buttons won't save — run api.py locally."
        : "Status buttons won't save — online API unavailable.";
    } else if (!state.apiHasSkip || !state.apiHasReplied) {
      apiMessage = "Restart api.py so Sent / Replied / Gone sync.";
    }
    els.apiHint.textContent = apiMessage;
    els.apiHint.hidden = !apiMessage;
    els.apiHint.classList.toggle("warn", Boolean(apiMessage));
  }

  const scrapeBtn = document.getElementById("scrape-btn");
  const scrapeSep = document.getElementById("scrape-sep");
  if (scrapeBtn) scrapeBtn.style.display = state.apiHasScrape ? "inline-block" : "none";
  if (scrapeSep) scrapeSep.hidden = !state.apiHasScrape;

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
    applyApplicationStatus(id, "rejected", true);
    setCachedStatus(id, "rejected");
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
    const status = json.status || "rejected";
    applyApplicationStatus(id, status, true);
    setCachedStatus(id, status);
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

async function markScam(id) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return;

  const base = apiBase();
  if (!base || !state.apiOnline) {
    const local = loadLocalDeletes();
    local.add(id);
    saveLocalDeletes(local);
    applyApplicationStatus(id, "rejected", true);
    setCachedStatus(id, "rejected");
    recalculateCounts();
    render();
    toast("Marked scam (saved in this browser)");
    return;
  }

  try {
    const res = await fetch(`${base}/api/scam/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) throw new Error(json.error || "Failed");
    const local = loadLocalDeletes();
    local.delete(id);
    saveLocalDeletes(local);
    const status = json.status || "rejected";
    applyApplicationStatus(id, status, true);
    setCachedStatus(id, status);
    recalculateCounts();
    render();
    toast("Marked as likely scam");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

async function revertListing(id) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return;

  const base = apiBase();
  if (!base || !state.apiOnline) {
    const local = loadLocalDeletes();
    local.delete(id);
    saveLocalDeletes(local);
    const skips = loadLocalSkips();
    skips.delete(id);
    saveLocalSkips(skips);
    
    clearCachedStatus(id);
    item.appStatus = null;
    item.queueStatus = "to_apply";
    item.appUpdatedAt = null;
    item.appSentAt = null;
    item.appRepliedAt = null;
    item.appTouredAt = null;
    item.appRejectedAt = null;
    item.appSkippedAt = null;
    recalculateCounts();
    render();
    toast("Reverted (saved in this browser)");
    return;
  }

  try {
    const res = await fetch(`${base}/api/revert/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) throw new Error(json.error || "Failed");
    
    clearCachedStatus(id);
    const local = loadLocalDeletes();
    local.delete(id);
    saveLocalDeletes(local);
    
    item.appStatus = null;
    item.queueStatus = "to_apply";
    item.appUpdatedAt = null;
    item.appSentAt = null;
    item.appRepliedAt = null;
    item.appTouredAt = null;
    item.appRejectedAt = null;
    item.appSkippedAt = null;
    recalculateCounts();
    render();
    toast("Listing reverted back to To Apply");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

async function saveListingMemo(id, text) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (item) {
    item.notes = text;
  }
  const base = apiBase();
  if (!base || !state.apiOnline) {
    toast("Memo saved in browser (run api.py to sync to DB)");
    return;
  }
  try {
    const res = await fetch(`${base}/api/notes/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: text }),
    });
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "Failed");
    toast("Memo saved successfully");
  } catch (err) {
    toast("Failed to save memo: " + err.message, true);
  }
}

async function markVisited(id) {
  const item = (state.data?.listings || []).find((row) => row.id === id);
  if (!item) return;

  const base = apiBase();
  if (!base || !state.apiOnline) {
    applyApplicationStatus(id, "toured", true);
    setCachedStatus(id, "toured");
    recalculateCounts();
    render();
    toast("Marked visited (saved in this browser)");
    return;
  }

  try {
    const res = await fetch(`${base}/api/toured/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) throw new Error(json.error || "Failed");
    
    const status = json.status || "toured";
    applyApplicationStatus(id, status, true);
    setCachedStatus(id, status);
    recalculateCounts();
    render();
    toast("Marked as Visited");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

async function markSkipped(id) {
  const base = apiBase();

  if (!base || !state.apiHasSkip) {
    const local = loadLocalSkips();
    local.add(id);
    saveLocalSkips(local);
    if (applySkipToItem(id)) {
      setCachedStatus(id, "skipped");
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
    const status = json.status || "skipped";
    applyApplicationStatus(id, status, true);
    setCachedStatus(id, status);
    recalculateCounts();
    render();
    toast("Skipped");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

async function markReplied(id) {
  const base = apiBase();
  if (!base || !state.apiOnline || !state.apiHasReplied) {
    applyApplicationStatus(id, "replied", true);
    setCachedStatus(id, "replied");
    recalculateCounts();
    render();
    toast("Marked replied (saved in this browser)");
    if (!base) return;
    if (!state.apiHasReplied) {
      toast("Restart api.py to sync status to database", true);
    }
    return;
  }
  try {
    const res = await fetch(`${base}/api/replied/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) throw new Error(json.error || "Failed");
    const status = json.status || "replied";
    applyApplicationStatus(id, status, true);
    setCachedStatus(id, status);
    recalculateCounts();
    render();
    toast("Marked as replied");
  } catch (err) {
    toast(String(err.message || err), true);
  }
}

async function markSent(id) {
  const base = apiBase();

  if (!base || !state.apiOnline) {
    applyApplicationStatus(id, "sent", true);
    setCachedStatus(id, "sent");
    recalculateCounts();
    render();
    toast("Marked sent (saved in this browser)");
    if (!base) return;
    return;
  }
  try {
    const res = await fetch(`${base}/api/sent/${encodeURIComponent(id)}`, { method: "POST" });
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "Failed");
    const status = json.status || "sent";
    applyApplicationStatus(id, status, true);
    setCachedStatus(id, status);
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
  els.memoOnly.addEventListener("change", () => {
    state.memoOnly = els.memoOnly.checked;
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
      renderDetailsCell(detailsEl, item, !detailsEl.classList.contains("expanded"));
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
    const scamBtn = event.target.closest(".scam-btn");
    if (scamBtn) {
      markScam(scamBtn.dataset.id);
      return;
    }
    const repliedBtn = event.target.closest(".replied-btn");
    if (repliedBtn) {
      markReplied(repliedBtn.dataset.id);
      return;
    }
    const visitedBtn = event.target.closest(".visited-btn");
    if (visitedBtn) {
      markVisited(visitedBtn.dataset.id);
      return;
    }
    const goneBtn = event.target.closest(".gone-btn");
    if (goneBtn) {
      markGone(goneBtn.dataset.id);
      return;
    }
    const revertBtn = event.target.closest(".revert-btn");
    if (revertBtn) {
      revertListing(revertBtn.dataset.id);
      return;
    }
    const sameHouseBtn = event.target.closest(".same-house-btn");
    if (sameHouseBtn) {
      const gId = sameHouseBtn.dataset.groupId;
      state.search = "group-" + gId;
      els.search.value = "group-" + gId;
      state.page = 1;
      render();
      toast("Filtering by same house listings");
      return;
    }
  });

  els.tbody.addEventListener("change", (event) => {
    const memoInput = event.target.closest(".memo-input");
    if (memoInput) {
      saveListingMemo(memoInput.dataset.id, memoInput.value);
    }
  });
}

let scrapingPollInterval = null;

async function checkScrapingStatus() {
  const base = apiBase();
  if (!base || !state.apiHasScrape) return;
  try {
    const res = await fetch(`${base}/api/scrape/status`);
    const json = await res.json();
    if (json.ok) {
      updateScrapeUI(json.is_scraping, json.status, json.error);
    }
  } catch (err) {
    console.error("Failed to check scraping status:", err);
  }
}

function updateScrapeUI(isScraping, status, error) {
  const btn = document.getElementById("scrape-btn");
  const statusEl = document.getElementById("scrape-status");
  const sep = document.getElementById("scrape-sep");
  if (!btn || !statusEl) return;

  if (isScraping) {
    btn.disabled = true;
    btn.textContent = "Scraping...";
    statusEl.textContent = "Scraping... this can take a minute.";
    statusEl.style.display = "inline-block";
    statusEl.style.color = "var(--orange)";

    if (!scrapingPollInterval) {
      scrapingPollInterval = setInterval(checkScrapingStatus, 2000);
    }
  } else {
    btn.disabled = false;
    btn.textContent = "Run Scrape";
    
    if (status === "success") {
      statusEl.textContent = "Scrape complete! Reloading...";
      statusEl.style.display = "inline-block";
      statusEl.style.color = "var(--green)";
      
      if (scrapingPollInterval) {
        clearInterval(scrapingPollInterval);
        scrapingPollInterval = null;
      }
      
      setTimeout(async () => {
        try {
          const dataRes = await fetch("./data.json?ts=" + Date.now());
          state.data = await dataRes.json();
          mergeLocalLikes();
          applyLocalDeletes();
          mergeLocalSkips();
          await syncApplicationStatuses();
          render();
          statusEl.style.display = "none";
          toast("Scrape successful and listings updated!");
        } catch (e) {
          toast("Failed to reload after scrape: " + e.message, true);
        }
      }, 1500);
    } else if (status === "failed") {
      statusEl.textContent = "Scrape failed: " + (error || "Unknown error");
      statusEl.style.display = "inline-block";
      statusEl.style.color = "var(--red)";
      
      if (scrapingPollInterval) {
        clearInterval(scrapingPollInterval);
        scrapingPollInterval = null;
      }
    } else {
      statusEl.style.display = "none";
    }
  }
}

async function triggerScrape() {
  const base = apiBase();
  if (!base || !state.apiHasScrape) return;
  try {
    const btn = document.getElementById("scrape-btn");
    if (btn) btn.disabled = true;
    
    const res = await fetch(`${base}/api/scrape`, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) throw new Error(json.error || "Failed");
    
    toast("Scrape initiated!");
    updateScrapeUI(true, "running", null);
  } catch (err) {
    toast("Failed to start scrape: " + err.message, true);
    updateScrapeUI(false, "failed", err.message);
  }
}

async function init() {
  state.lastClickedId = loadLastClickedId();
  const res = await fetch("./data.json?ts=" + Date.now());
  state.data = await res.json();
  mergeLocalLikes();
  applyLocalDeletes();
  mergeLocalSkips();
  applyStatusCache();
  await checkApi();
  const synced = await syncApplicationStatuses();
  if (!synced) applyStatusCache();
  bindControls();

  const scrapeBtn = document.getElementById("scrape-btn");
  if (scrapeBtn) {
    scrapeBtn.addEventListener("click", triggerScrape);
    if (state.apiHasScrape) {
      checkScrapingStatus();
    }
  }

  render();
  if (state.lastClickedId) {
    highlightLastClickedRow({ scroll: true });
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    syncApplicationStatuses().then((synced) => {
      if (!synced) applyStatusCache();
      render();
    });
    if (state.lastClickedId) {
      highlightLastClickedRow({ scroll: true, pulse: true });
    }
  });
}

init().catch((err) => {
  els.tbody.innerHTML = `<tr><td colspan="14" class="hint">Failed to load queue: ${esc(err.message)}</td></tr>`;
});
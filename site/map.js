const state = {
  data: null,
  search: "",
  tab: "to_apply",
  source: "all",
  bath: "all",
  maxPrice: "",
  likedOnly: false,
  memoOnly: false,
  multiRoomOnly: false,
  excludeScam: document.getElementById("filter-scam")?.checked ?? false,
  findNote: "",
  userId: "",
  users: [],
  selectedId: "",
  map: null,
  layer: null,
  markers: new Map(),
  pins: [],
  skipFit: false,
  fitting: false,
};

const USER_STORAGE_KEY = "lfr-active-user";
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function toast(text, isError = false) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = text;
  el.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.className = "toast"; }, 4200);
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

function apiHeaders(extra) {
  const headers = { ...(extra || {}) };
  if (state.userId) headers["X-LFR-User"] = state.userId;
  return headers;
}

async function apiFetch(path, options = {}) {
  const base = apiBase();
  if (!base) throw new Error("API offline");
  const { headers: extraHeaders, ...rest } = options;
  return fetch(`${base}${path}`, {
    credentials: "same-origin",
    ...rest,
    headers: apiHeaders(extraHeaders),
  });
}

function normalizeArea(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/facebook\s*·\s*/g, "")
    .replace(/,?\s*(?:san francisco|sf)?\s*,?\s*ca(?:lifornia)?\s*$/g, "")
    .replace(/,?\s*san francisco\s*$/g, "")
    .replace(/[/,·]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function mapAreas() {
  return state.data?.mapAreas || {};
}

function lookupArea(text) {
  const areas = mapAreas();
  const normalized = normalizeArea(text);
  if (!normalized) return null;
  if (areas[normalized]) return { name: normalized, ...areas[normalized] };
  let best = null;
  for (const [name, info] of Object.entries(areas)) {
    if (name.length < 4) continue;
    if (normalized.includes(name) || name.includes(normalized)) {
      if (!best || name.length > best.name.length) {
        best = { name, ...info };
      }
    }
  }
  return best;
}

function hasStreetAddress(item) {
  const blob = [item.rentalAddress, item.displayAddress, item.neighborhood].filter(Boolean).join(" ");
  return /\b\d{1,5}\s+[\w'.-]+(?:\s+[\w'.-]+){0,4}\s+(?:st|street|str|ave|avenue|av|rd|road|blvd|boulevard|dr|drive|ln|lane|way|ct|court|pl|place)\b/i.test(blob);
}

function resolvePoint(item) {
  if (Number.isFinite(item.lat) && Number.isFinite(item.lng)) {
    const street = item.coordSource === "street" || hasStreetAddress(item);
    return {
      lat: item.lat,
      lng: item.lng,
      source: street ? "street" : (item.coordSource || "export"),
      area: item.mapArea || "",
      radius: Number(mapAreas()[item.mapArea]?.radius) || 0.0032,
    };
  }
  const fields = [item.neighborhood, item.rentalAddress, item.displayAddress, item.title, item.city];
  for (const field of fields) {
    const match = lookupArea(field);
    if (match) {
      return {
        lat: match.lat,
        lng: match.lng,
        source: "neighborhood",
        area: match.name,
        radius: Number(match.radius) || 0.0032,
      };
    }
  }
  return null;
}

function scatterOffset(index, count, radiusDeg, lat) {
  const n = Math.max(count, 1);
  const t = (index + 1) / (n + 1);
  const radius = radiusDeg * (0.28 + 0.72 * Math.sqrt(t));
  const theta = index * GOLDEN_ANGLE;
  const dlat = radius * Math.cos(theta);
  const cosLat = Math.cos((lat * Math.PI) / 180) || 1;
  const dlng = (radius * Math.sin(theta)) / cosLat;
  return [dlat, dlng];
}

function pinPositions(items) {
  const groups = new Map();
  const resolved = items.map((item) => {
    const point = resolvePoint(item);
    return { item, point };
  }).filter((row) => row.point);

  for (const row of resolved) {
    const key = row.point.area || `${row.point.lat.toFixed(4)},${row.point.lng.toFixed(4)}`;
    const street = row.point.source === "street" || hasStreetAddress(row.item);
    const approx = !street && (row.point.source === "neighborhood" || row.point.source === "city" || row.item.coordApprox);
    if (!approx) continue;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  for (const members of groups.values()) {
    members.sort((a, b) => String(a.item.id).localeCompare(String(b.item.id)));
    const radius = members[0].point.radius || 0.0032;
    const lat = members[0].point.lat;
    members.forEach((row, index) => {
      const [dlat, dlng] = scatterOffset(index, members.length, radius, lat);
      row.point = {
        ...row.point,
        lat: lat + dlat,
        lng: row.point.lng + dlng,
        approx: true,
      };
    });
  }
  return resolved;
}

function sourceLabel(item) {
  if (item.source === "facebook") return "Facebook";
  if (item.source === "zillow") return "Zillow";
  if (item.source === "craigslist") return "Craigslist";
  return item.source || "Craigslist";
}

function statusLabel(item) {
  switch (item.queueStatus) {
    case "applied": return "Applied";
    case "replied": return "Replied";
    case "visited": return "Visited";
    case "skipped": return "Skipped";
    case "gone": return "Gone";
    default: return "To apply";
  }
}

function searchBlob(item) {
  // Keep this in step with the queue's searchBlob in app.js — the same typed
  // text should match the same listings in both views.
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
    item.isMultiRoomHouse ? "multiple rooms in house" : "",
    item.scamLikely ? "scam likely" : "",
    item.scamWhy || "",
    item.posterName ? "author-" + item.posterName : "",
    sourceLabel(item),
    item.queueStatus || "",
  ].filter(Boolean).join(" ").toLowerCase();
}

const EXCLUDED_AREA_RE = /\b(bayview|bay view|hunters point|hunter'?s point|portola|visitacion valley)\b/i;
const EXCLUDED_ZIP_RE = /\b94124\b|\b94134\b/;
const PIN_FILL = "#ffc078";
const PIN_STROKE = "#e0892e";
const PIN_SELECTED_FILL = "#ffb347";
const PIN_SELECTED_STROKE = "#c2410c";

function isExcludedArea(item) {
  const blob = [
    item.neighborhood,
    item.displayAddress,
    item.rentalAddress,
    item.mapArea,
    item.city,
    item.zip,
  ].filter(Boolean).join(" ");
  return EXCLUDED_ZIP_RE.test(blob) || EXCLUDED_AREA_RE.test(blob);
}

function passesFilters(item) {
  if (state.tab !== "all" && (item.queueStatus || "to_apply") !== state.tab) return false;
  if (state.likedOnly && !item.liked) return false;
  if (state.memoOnly && !item.notes) return false;
  if (state.multiRoomOnly && !item.isMultiRoomHouse) return false;
  if (state.excludeScam && item.scamLikely) return false;
  if (isExcludedArea(item)) return false;
  if (state.source !== "all" && item.source !== state.source) return false;
  if (state.bath && state.bath !== "all") {
    const privacy = String(item.bathPrivacy || "unknown");
    if (privacy !== state.bath) return false;
  }
  const maxPrice = state.maxPrice === "" ? null : Number(state.maxPrice);
  if (maxPrice !== null && Number.isFinite(maxPrice)) {
    const price = Number(item.price);
    if (!Number.isFinite(price) || price > maxPrice) return false;
  }
  const q = state.search.trim().toLowerCase();
  if (q && !searchBlob(item).includes(q)) return false;
  return true;
}

function filteredItems() {
  const items = (state.data?.listings || []).filter(passesFilters);
  items.sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0));
  return items;
}

function popupHtml(item, point) {
  const price = item.price ? `$${item.price}/mo` : "—";
  const sqft = item.sqftLabel || "—";
  const approx = point?.approx || item.coordApprox || point?.source === "neighborhood" || point?.source === "city";
  const approxNote = approx
    ? `<em style="color:#6e6e73">Approx. — placed in ${esc(item.neighborhood || point?.area || "this neighborhood")}</em><br>`
    : "";
  return `
    <div style="min-width:12rem;line-height:1.4">
      <strong><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a></strong><br>
      ${esc(price)} · ${esc(item.neighborhood || "—")}<br>
      Sqft: ${esc(sqft)} · Score: ${esc(item.scoreLabel ?? item.score ?? "—")}<br>
      ${approxNote}
      ${item.liked ? "★ Liked<br>" : ""}
    </div>`;
}

function listingById(id) {
  return (state.data?.listings || []).find((row) => row.id === id);
}

function listCardHtml(item, index) {
  const price = item.price ? `$${item.price}` : "—";
  const tags = [];
  if (item.scamLikely) tags.push(`<span class="tag-inline tag-scam" title="${esc(item.scamWhy || "Matches a marked scam")}">⚠️ Likely scam</span>`);
  if (item.layoutLabel) tags.push(`<span class="tag-inline">${esc(item.layoutLabel)}</span>`);
  if (item.bathPrivacy === "private") tags.push(`<span class="tag-inline">Private bath</span>`);
  if (item.isMultiRoomHouse) {
    tags.push(`<span class="tag-inline tag-rooms">${esc(item.roomsInHouse || 2)} rooms in house</span>`);
  }
  if (item.liked) tags.push(`<span class="tag-inline">★ Liked</span>`);
  const cls = [
    "map-list-item",
    item.id === state.selectedId ? "active" : "",
  ].filter(Boolean).join(" ");
  return `
    <article class="${cls}" data-id="${esc(item.id)}" tabindex="0">
      <div class="map-list-top">
        <span>${index}. ${esc(price)}${item.price ? "/mo" : ""} · ${esc(statusLabel(item))}</span>
        <span>Score ${esc(item.scoreLabel ?? item.score ?? "—")}</span>
      </div>
      <div class="map-list-title">${esc(item.title)}</div>
      <div class="map-list-meta">${esc(item.displayAddress || item.neighborhood || "—")} · ${esc(sourceLabel(item))}${item.moveInLabel ? ` · ${esc(item.moveInLabel)}` : ""}</div>
      ${tags.length ? `<div class="map-list-tags">${tags.join("")}</div>` : ""}
      ${item.url ? `<a class="map-list-open" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Open listing</a>` : ""}
    </article>`;
}

function highlightListItem(id, { scroll = false } = {}) {
  document.querySelectorAll(".map-list-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === id);
  });
  if (!scroll) return;
  const active = document.querySelector(`.map-list-item[data-id="${CSS.escape(String(id))}"]`);
  if (active) active.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function selectListing(id, { openPopup = true, pan = true } = {}) {
  state.selectedId = id || "";
  restylePins();
  const marker = state.markers.get(id);
  if (marker && state.map) {
    if (pan) {
      state.skipFit = true;
      state.map.setView(marker.getLatLng(), Math.max(state.map.getZoom(), 14), { animate: true });
    }
    if (openPopup) marker.openPopup();
  }
  syncListToMap({ scrollToSelected: true });
}

// Pins are geographic circles on purpose — their size shows how vague the
// location is. That means they balloon on screen as you zoom in (280 m is
// ~18px at zoom 13 but ~300px at zoom 17, covering the map), so clamp the
// drawn radius to a sane pixel range at the current zoom.
const PIN_MAX_PX = 11;

function metersPerPixel(lat) {
  const zoom = state.map ? state.map.getZoom() : 13;
  return (40075016.686 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, zoom + 8);
}

function markerMeters(item, point) {
  const selected = item.id === state.selectedId;
  const base = point?.source === "street"
    ? (selected ? 90 : 75)
    : (selected ? 160 : 140);
  // Only ever shrink. L.circle.getBounds() includes the radius, so a pin that
  // is allowed to grow past its true size drags the initial fitBounds out with
  // it — at the pre-fit zoom that means circles hundreds of km wide.
  const perPixel = metersPerPixel(Number.isFinite(point?.lat) ? point.lat : 37.77);
  return Math.min(base, PIN_MAX_PX * perPixel);
}

function markerStyle(item) {
  const selected = item.id === state.selectedId;
  return {
    color: selected ? PIN_SELECTED_STROKE : PIN_STROKE,
    fillColor: selected || item.liked ? PIN_SELECTED_FILL : PIN_FILL,
    fillOpacity: selected ? 0.45 : 0.32,
    weight: selected ? 3 : 2,
    opacity: 1,
  };
}

function restylePins() {
  if (!state.map) return;
  for (const pin of state.pins) {
    const marker = state.markers.get(pin.id);
    if (!marker) continue;
    marker.setStyle(markerStyle(pin.item));
    if (typeof marker.setRadius === "function") {
      marker.setRadius(markerMeters(pin.item, pin.point));
    }
  }
}

function itemsInMapView() {
  if (!state.map || !state.pins.length) return [];
  const bounds = state.map.getBounds();
  if (!bounds || !bounds.isValid()) return [];
  const items = [];
  for (const pin of state.pins) {
    if (!bounds.contains(L.latLng(pin.lat, pin.lng))) continue;
    items.push(pin.item);
  }
  items.sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0));
  return items;
}

function renderList(items, { scrollToSelected = false } = {}) {
  const root = document.getElementById("map-list");
  if (!root) return;
  if (!items.length) {
    root.innerHTML = '<div class="map-list-empty">No homes in this map area. Pan or zoom to see more.</div>';
    return;
  }
  root.innerHTML = items.map((item, i) => listCardHtml(item, i + 1)).join("");
  if (state.selectedId) highlightListItem(state.selectedId, { scroll: scrollToSelected });
}

function syncListToMap(opts = {}) {
  const items = itemsInMapView();
  const pinEl = document.getElementById("pin-count");
  const hintEl = document.getElementById("map-hint");
  const onMap = state.pins.length;
  if (pinEl) pinEl.textContent = `${items.length} in view · ${onMap} on map`;
  if (hintEl) {
    hintEl.className = "map-legend map-legend-info";
    hintEl.textContent = onMap ? "" : "No mappable listings match your filters.";
  }
  renderList(items, opts);
}

function renderPins(items, { fit = true } = {}) {
  const pins = pinPositions(items);
  state.pins = pins.map(({ item, point }) => ({
    id: item.id,
    lat: point.lat,
    lng: point.lng,
    item,
    point,
  }));
  if (!state.map) {
    syncListToMap();
    return;
  }
  if (state.layer) state.layer.clearLayers();
  state.markers = new Map();

  const markers = [];
  for (const { item, point } of pins) {
    const marker = L.circle([point.lat, point.lng], {
      radius: markerMeters(item, point),
      ...markerStyle(item),
    });
    marker.bindPopup(popupHtml(item, point));
    marker.on("click", () => selectListing(item.id, { openPopup: false, pan: false }));
    marker.addTo(state.layer);
    state.markers.set(item.id, marker);
    markers.push(marker);
  }

  const shouldFit = markers.length && fit && !state.skipFit;
  state.skipFit = false;
  if (shouldFit) {
    state.fitting = true;
    const group = L.featureGroup(markers);
    // Note: do not invalidateSize() here. L.Circle.getBounds() converts cached
    // projected pixel points back to lat/lng, so re-measuring the container
    // first invalidates them and the fit lands somewhere else entirely. The
    // pane is given a height floor in CSS so it is never measured collapsed.
    state.map.fitBounds(group.getBounds().pad(0.08));
    const done = () => {
      state.fitting = false;
      restylePins();
      syncListToMap();
    };
    state.map.once("moveend", done);
    setTimeout(done, 400);
  } else {
    syncListToMap();
  }
}

function render() {
  renderPins(filteredItems(), { fit: true });
}

function initMap() {
  state.map = L.map("map").setView([37.79, -122.32], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    maxZoom: 18,
  }).addTo(state.map);
  state.layer = L.layerGroup().addTo(state.map);
  let moveTick = 0;
  const onViewChange = () => {
    if (state.fitting) return;
    const now = Date.now();
    if (now - moveTick < 40) return;
    moveTick = now;
    syncListToMap();
  };
  state.map.on("move", onViewChange);
  state.map.on("zoom", onViewChange);
  state.map.on("moveend", () => {
    if (state.fitting) return;
    syncListToMap();
  });
  state.map.on("zoomend", () => {
    restylePins();
    if (state.fitting) return;
    syncListToMap();
  });
  requestAnimationFrame(() => state.map.invalidateSize());
}


function bindControls() {
  const rerender = () => render();
  document.getElementById("filter-search")?.addEventListener("input", (event) => {
    state.search = event.target.value;
    rerender();
  });
  document.getElementById("filter-status")?.addEventListener("change", (event) => {
    state.tab = event.target.value;
    rerender();
  });
  document.getElementById("filter-source")?.addEventListener("change", (event) => {
    state.source = event.target.value;
    rerender();
  });
  document.getElementById("filter-bath")?.addEventListener("change", (event) => {
    state.bath = event.target.value;
    rerender();
  });
  document.getElementById("filter-price")?.addEventListener("input", (event) => {
    state.maxPrice = event.target.value;
    rerender();
  });
  document.getElementById("filter-liked")?.addEventListener("change", (event) => {
    state.likedOnly = event.target.checked;
    rerender();
  });
  document.getElementById("filter-memo")?.addEventListener("change", (event) => {
    state.memoOnly = event.target.checked;
    rerender();
  });
  document.getElementById("filter-multiroom")?.addEventListener("change", (event) => {
    state.multiRoomOnly = event.target.checked;
    rerender();
  });
  document.getElementById("filter-scam")?.addEventListener("change", (event) => {
    state.excludeScam = event.target.checked;
    rerender();
  });
  document.getElementById("map-list")?.addEventListener("click", (event) => {
    if (event.target.closest(".map-list-open")) return;
    const card = event.target.closest(".map-list-item");
    if (!card?.dataset.id) return;
    state.skipFit = true;
    selectListing(card.dataset.id);
  });
}

function applyPageBranding() {
  const title = (state.data?.pageTitle || "").trim() || "Listing map";
  document.title = title.includes("map") ? title : `${title} — Map`;
  const heading = document.getElementById("page-title");
  if (heading) heading.textContent = title.includes("map") ? title : `${title} — Map`;
  const back = document.getElementById("back-to-queue");
  if (back && state.data?.pageTitle) {
    back.textContent = `Back to ${state.data.pageTitle}`;
  }
}

function fillUserSelect() {
  const sel = document.getElementById("user-select");
  if (!sel) return;
  const users = state.users || [];
  sel.innerHTML = users.map((user) => {
    const budget = user.budget ? ` ($${user.budget})` : "";
    const selected = user.id === state.userId ? " selected" : "";
    return `<option value="${esc(user.id)}"${selected}>${esc(user.name)}${budget}</option>`;
  }).join("");
  sel.hidden = users.length === 0;
}

async function loadQueueData() {
  const candidates = [];
  if (state.userId) candidates.push(`./data-${state.userId}.json`);
  candidates.push("./data.json");
  for (const url of candidates) {
    try {
      const res = await fetch(`${url}?ts=${Date.now()}`);
      if (!res.ok) continue;
      const payload = await res.json();
      state.data = payload;
      if (payload?.userId) state.userId = payload.userId;
      if (Array.isArray(payload?.users) && payload.users.length) state.users = payload.users;
      fillUserSelect();
      return;
    } catch (_) { /* try next */ }
  }
  state.data = { listings: [] };
}

async function init() {
  initMap();
  state.userId = localStorage.getItem(USER_STORAGE_KEY) || "";
  try {
    const res = await fetch("./users.json?ts=" + Date.now());
    if (res.ok) {
      const json = await res.json();
      state.users = json.users || [];
      if (!state.userId) state.userId = json.active || "";
    }
  } catch (_) { /* ignore */ }
  await loadQueueData();
  applyPageBranding();
  bindControls();
  const userSelect = document.getElementById("user-select");
  if (userSelect) {
    userSelect.addEventListener("change", async () => {
      state.userId = userSelect.value;
      localStorage.setItem(USER_STORAGE_KEY, state.userId);
      await loadQueueData();
      applyPageBranding();
      render();
    });
  }
  window.addEventListener("resize", () => {
    if (state.map) state.map.invalidateSize();
  });
  render();
  setTimeout(() => state.map && state.map.invalidateSize(), 80);
}

init().catch((err) => {
  const hint = document.getElementById("map-hint");
  if (hint) {
    hint.className = "map-legend map-legend-error";
    hint.textContent = `Failed to load map data: ${err.message}`;
  }
});

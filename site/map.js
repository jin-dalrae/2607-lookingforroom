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
  findIds: null,
  findNote: "",
  findQuery: "",
  userId: "",
  users: [],
  selectedId: "",
  map: null,
  layer: null,
  markers: new Map(),
  skipFit: false,
  ignoreMove: false,
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
  return [
    item.title,
    item.price ? String(item.price) : "",
    item.displayAddress,
    item.rentalAddress,
    item.neighborhood,
    item.city,
    item.transitTag,
    item.moveInLabel,
    item.posterName,
    item.details,
    item.notes,
    item.isMultiRoomHouse ? "multiple rooms in house" : "",
    sourceLabel(item),
  ].filter(Boolean).join(" ").toLowerCase();
}

function passesFilters(item) {
  if (!state.findIds && state.tab !== "all" && (item.queueStatus || "to_apply") !== state.tab) return false;
  if (state.likedOnly && !item.liked) return false;
  if (state.memoOnly && !item.notes) return false;
  if (state.multiRoomOnly && !item.isMultiRoomHouse) return false;
  if (state.findIds && !state.findIds.has(item.id)) return false;
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

function highlightListItem(id) {
  document.querySelectorAll(".map-list-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === id);
  });
  const active = document.querySelector(`.map-list-item[data-id="${CSS.escape(id)}"]`);
  if (active) {
    active.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function selectListing(id, { openPopup = true, pan = true } = {}) {
  state.selectedId = id || "";
  highlightListItem(id);
  const marker = state.markers.get(id);
  if (marker && state.map) {
    if (pan) state.map.setView(marker.getLatLng(), Math.max(state.map.getZoom(), 14), { animate: true });
    if (openPopup) marker.openPopup();
  }
}

function visibleMapItems() {
  if (!state.map || !state.markers.size) return [];
  const bounds = state.map.getBounds().pad(0.02);
  const items = [];
  for (const [id, marker] of state.markers) {
    const latlng = marker.getLatLng();
    if (!bounds.contains(latlng)) continue;
    const item = listingById(id);
    if (item) items.push(item);
  }
  items.sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0));
  return items;
}

function renderList(items) {
  const root = document.getElementById("map-list");
  if (!root) return;
  if (!items.length) {
    root.innerHTML = '<div class="map-list-empty">No homes in this map area. Pan or zoom to see more.</div>';
    return;
  }
  root.innerHTML = items.map((item, i) => listCardHtml(item, i + 1)).join("");
  if (state.selectedId) highlightListItem(state.selectedId);
}

function updateVisibleList() {
  const items = visibleMapItems();
  const pinEl = document.getElementById("pin-count");
  const hintEl = document.getElementById("map-hint");
  const onMap = state.markers.size;
  if (pinEl) pinEl.textContent = `${items.length} in view · ${onMap} on map`;
  if (hintEl) {
    hintEl.textContent = onMap
      ? "List shows only homes in the current map. Pan or zoom to update."
      : "No mappable listings match your filters.";
  }
  renderList(items);
}

function renderPins(items, { fit = true } = {}) {
  const pins = pinPositions(items);
  if (!state.map) {
    updateVisibleList();
    return;
  }
  if (state.layer) state.layer.clearLayers();
  state.markers = new Map();

  const markers = [];
  for (const { item, point } of pins) {
    const approx = point.approx || item.coordApprox || point.source === "neighborhood" || point.source === "city";
    const marker = L.circleMarker([point.lat, point.lng], {
      radius: item.liked ? 8 : approx ? 7 : 6,
      color: item.id === state.selectedId ? "#c88700" : item.liked ? "#c88700" : "#0071e3",
      fillColor: item.isMatch ? "#248a3d" : item.liked ? "#e8a317" : "#0071e3",
      fillOpacity: approx ? 0.55 : 0.85,
      weight: 2,
      dashArray: approx ? "4,3" : null,
    });
    marker.bindPopup(popupHtml(item, point));
    marker.on("click", () => selectListing(item.id, { openPopup: false, pan: false }));
    marker.addTo(state.layer);
    state.markers.set(item.id, marker);
    markers.push(marker);
  }

  if (markers.length && fit && !state.skipFit) {
    state.ignoreMove = true;
    const group = L.featureGroup(markers);
    state.map.fitBounds(group.getBounds().pad(0.12));
    const finishFit = () => {
      if (!state.ignoreMove) return;
      state.ignoreMove = false;
      updateVisibleList();
    };
    state.map.once("moveend", finishFit);
    setTimeout(finishFit, 350);
  } else {
    updateVisibleList();
  }
  state.skipFit = false;
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
  state.map.on("moveend", () => {
    if (state.ignoreMove) return;
    updateVisibleList();
  });
  requestAnimationFrame(() => state.map.invalidateSize());
}

function setFindStatus(text, mode) {
  const status = document.getElementById("find-status");
  const form = document.getElementById("find-form");
  const clear = document.getElementById("find-clear");
  if (status) status.textContent = text || "";
  if (form) {
    form.classList.toggle("is-finding", mode === "finding");
    form.classList.toggle("has-results", mode === "results");
  }
  if (clear) clear.hidden = !state.findIds;
}

function clearFind() {
  state.findIds = null;
  state.findNote = "";
  state.findQuery = "";
  const input = document.getElementById("find-query");
  const btn = document.getElementById("find-btn");
  if (input) input.value = "";
  if (btn) btn.disabled = false;
  setFindStatus("", "");
  render();
}

function runFind(event) {
  if (event) event.preventDefault();
  const input = document.getElementById("find-query");
  const question = (input?.value || "").trim();
  if (!question) {
    clearFind();
    return;
  }
  const listings = state.data?.listings || [];
  if (!listings.length) {
    toast("No listings loaded yet", true);
    return;
  }
  if (!window.LfrFind) {
    toast("Find is not loaded", true);
    return;
  }
  const result = window.LfrFind.findListings(question, listings);
  const ids = result.ids || [];
  state.findIds = new Set(ids);
  state.findNote = result.note || "";
  state.findQuery = question;
  setFindStatus(result.note || "", ids.length ? "results" : "");
  render();
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
  document.getElementById("find-form")?.addEventListener("submit", (event) => runFind(event));
  document.getElementById("find-query")?.addEventListener("input", (event) => {
    if (!event.target.value.trim()) {
      if (state.findIds) clearFind();
      return;
    }
    runFind();
  });
  document.getElementById("find-clear")?.addEventListener("click", () => clearFind());
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
  if (hint) hint.textContent = `Failed to load map data: ${err.message}`;
});

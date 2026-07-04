const state = {
  data: null,
  search: "",
  likedOnly: false,

  map: null,
  layer: null,
};

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function passesFilters(item) {
  if (!Number.isFinite(item.lat) || !Number.isFinite(item.lng)) return false;
  if (state.likedOnly && !item.liked) return false;

  const q = state.search.trim().toLowerCase();
  if (!q) return true;
  const blob = [
    item.title,
    item.neighborhood,
    item.rentalAddress,
    item.city,
  ].filter(Boolean).join(" ").toLowerCase();
  return blob.includes(q);
}

function popupHtml(item) {
  const price = item.price ? `$${item.price}/mo` : "—";
  const sqft = item.sqftLabel || "—";
  return `
    <div style="min-width:12rem;line-height:1.4">
      <strong><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a></strong><br>
      ${esc(price)} · ${esc(item.neighborhood || "—")}<br>
      Sqft: ${esc(sqft)} · Score: ${esc(item.scoreLabel ?? item.score ?? "—")}<br>
      ${item.liked ? "★ Liked<br>" : ""}
      <a href="/">Back to list</a>
    </div>`;
}

function renderPins() {
  const items = (state.data?.listings || []).filter(passesFilters);
  document.getElementById("pin-count").textContent = `${items.length} pins`;
  document.getElementById("map-hint").textContent = items.length
    ? "Click a pin for details. Zoom in for overlapping areas."
    : "No mappable listings match your filters.";

  if (!state.map) return;
  if (state.layer) state.layer.clearLayers();

  const markers = [];
  for (const item of items) {
    const marker = L.circleMarker([item.lat, item.lng], {
      radius: item.liked ? 8 : 6,
      color: item.liked ? "#c88700" : "#0071e3",
      fillColor: item.isMatch ? "#248a3d" : item.liked ? "#e8a317" : "#0071e3",
      fillOpacity: 0.85,
      weight: 2,
    });
    marker.bindPopup(popupHtml(item));
    marker.addTo(state.layer);
    markers.push(marker);
  }

  if (markers.length) {
    const group = L.featureGroup(markers);
    state.map.fitBounds(group.getBounds().pad(0.12));
  }
}

function initMap() {
  state.map = L.map("map").setView([37.79, -122.32], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    maxZoom: 18,
  }).addTo(state.map);
  state.layer = L.layerGroup().addTo(state.map);
}

function bindControls() {
  document.getElementById("filter-search").addEventListener("input", (event) => {
    state.search = event.target.value;
    renderPins();
  });
  document.getElementById("filter-liked").addEventListener("change", (event) => {
    state.likedOnly = event.target.checked;
    renderPins();
  });

}

async function init() {
  initMap();
  const res = await fetch("./data.json?ts=" + Date.now());
  state.data = await res.json();
  bindControls();
  renderPins();
}

init().catch((err) => {
  document.getElementById("map-hint").textContent = `Failed to load map data: ${err.message}`;
});
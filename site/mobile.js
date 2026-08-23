/** Small-screen behaviour shared by the queue and map pages: collapsible
 *  filters, a sort control that replaces the table headers, and a map/list
 *  switch. Everything is defensive — each page only has some of these. */
(function () {
  const mq = window.matchMedia("(max-width: 720px)");

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  // --- Collapsible filters -------------------------------------------------
  // Search and status stay visible (they are how you navigate the queue);
  // everything else folds behind a "Filters" button on a phone.
  function setupFilters() {
    const toolbar = document.querySelector(".toolbar");
    if (!toolbar) return;
    const isMapPage = !!document.querySelector(".map-split");

    // The map page folds every control away so the map itself gets the screen.
    // The queue page keeps search and status out, since it scrolls anyway and
    // those are how you move between statuses.
    const panels = [toolbar];
    if (!isMapPage) {
      ["filter-search", "filter-status"].forEach((id) => {
        document.getElementById(id)?.closest("label")?.classList.add("toolbar-primary");
      });
    }

    const toggle = el("button", "filters-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    panels.forEach((panel, i) => {
      if (!panel.id) panel.id = `lfr-panel-${i}`;
      panel.classList.add("is-collapsed");
    });
    toggle.setAttribute("aria-controls", panels.map((p) => p.id).join(" "));
    panels[0].parentNode.insertBefore(toggle, panels[0]);

    function activeCount() {
      let n = 0;
      if (document.getElementById("filter-source")?.value !== "all") n += 1;
      if (document.getElementById("filter-bath")?.value !== "all") n += 1;
      if ((document.getElementById("filter-price")?.value || "").trim()) n += 1;
      ["filter-liked", "filter-memo", "filter-multiroom", "filter-scam"].forEach((id) => {
        if (document.getElementById(id)?.checked) n += 1;
      });
      return n;
    }

    const name = isMapPage ? "Search & filters" : "Filters";

    function syncLabel() {
      const n = activeCount();
      const open = !toolbar.classList.contains("is-collapsed");
      toggle.textContent = n ? `${name} · ${n}` : name;
      toggle.classList.toggle("has-active", n > 0);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    }

    toggle.addEventListener("click", () => {
      const collapse = !toolbar.classList.contains("is-collapsed");
      panels.forEach((panel) => panel.classList.toggle("is-collapsed", collapse));
      syncLabel();
    });
    toolbar.addEventListener("change", syncLabel);
    toolbar.addEventListener("input", syncLabel);
    syncLabel();
  }

  // --- Mobile sort ---------------------------------------------------------
  // The table headers are the only sort UI, and they are hidden once rows
  // become cards. Rather than duplicate the sort logic, this drives the same
  // <th> click handlers the desktop table already uses.
  function setupSort() {
    const table = document.getElementById("queue-table");
    if (!table) return;
    const headers = Array.from(table.querySelectorAll("thead th[data-sort]"))
      .filter((th) => th.dataset.sort !== "liked");
    if (!headers.length) return;

    const bar = el("div", "mobile-sort");
    const label = el("label", "mobile-sort-label", "Sort");
    const select = el("select");
    headers.forEach((th) => {
      const opt = el("option", null, (th.textContent || "").replace(/[▲▼]/g, "").trim());
      opt.value = th.dataset.sort;
      select.appendChild(opt);
    });
    label.appendChild(select);

    const dir = el("button", "mobile-sort-dir");
    dir.type = "button";
    dir.title = "Reverse sort order";

    bar.appendChild(label);
    bar.appendChild(dir);
    table.parentNode.insertBefore(bar, table);

    const sortedHeader = () =>
      headers.find((th) => th.classList.contains("sorted-asc") || th.classList.contains("sorted-desc"));

    function sync() {
      const th = sortedHeader();
      if (!th) return;
      select.value = th.dataset.sort;
      const asc = th.classList.contains("sorted-asc");
      dir.textContent = asc ? "▲" : "▼";
      dir.setAttribute("aria-label", asc ? "Ascending — tap to reverse" : "Descending — tap to reverse");
    }

    select.addEventListener("change", () => {
      const th = headers.find((h) => h.dataset.sort === select.value);
      // Clicking the already-sorted header would only flip direction.
      if (th && th !== sortedHeader()) th.click();
    });
    dir.addEventListener("click", () => sortedHeader()?.click());

    // app.js rewrites the sorted-* classes on every render.
    new MutationObserver(sync).observe(table.querySelector("thead"), {
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    sync();
  }

  // --- Map / list switch ---------------------------------------------------
  // The split view has no room for two panes on a phone, so show one at a time.
  function setupMapSwitch() {
    const split = document.querySelector(".map-split");
    if (!split) return;

    const bar = el("div", "map-switch");
    const mapBtn = el("button", "map-switch-btn", "Map");
    const listBtn = el("button", "map-switch-btn", "List");
    mapBtn.type = "button";
    listBtn.type = "button";
    bar.appendChild(mapBtn);
    bar.appendChild(listBtn);
    split.parentNode.insertBefore(bar, split);

    function show(view) {
      split.dataset.mobileView = view;
      mapBtn.classList.toggle("active", view === "map");
      listBtn.classList.toggle("active", view === "list");
      mapBtn.setAttribute("aria-pressed", String(view === "map"));
      listBtn.setAttribute("aria-pressed", String(view === "list"));
      // map.js re-fits Leaflet on window resize; reuse that instead of
      // reaching into its map instance.
      if (view === "map") window.dispatchEvent(new Event("resize"));
    }

    mapBtn.addEventListener("click", () => show("map"));
    listBtn.addEventListener("click", () => show("list"));
    show("map");

    // Tapping a pin is only useful if the list it selects is visible.
    split.querySelector(".map-pane")?.addEventListener("click", (event) => {
      if (!mq.matches) return;
      if (event.target.closest(".leaflet-popup")) show("list");
    });
  }

  function init() {
    setupFilters();
    setupSort();
    setupMapSwitch();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

const ID_RE = /^[A-Za-z0-9._-]+$/;

const ENDPOINTS = [
  "sent",
  "replied",
  "skip",
  "like",
  "delete",
  "statuses",
  "scam",
  "revert",
  "notes",
  "toured",
  "accepted",
  "find",
];

const GEMINI_MODELS = [
  "gemini-2.5-flash",
  "gemini-2.0-flash",
  "gemini-1.5-flash",
  "gemini-2.5-flash-lite",
];

const MILESTONE_COL = {
  sent: "sent_at",
  replied: "replied_at",
  toured: "toured_at",
  rejected: "rejected_at",
  skipped: "skipped_at",
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

function jsonError(status, message) {
  return jsonResponse({ ok: false, error: message }, status);
}

function nowIso() {
  return new Date().toISOString();
}

function validId(id) {
  return typeof id === "string" && ID_RE.test(id);
}

async function readJson(request) {
  try {
    const body = await request.json();
    return body && typeof body === "object" ? body : {};
  } catch (_) {
    return {};
  }
}

async function transitionApplication(db, listingId, status, extra = {}) {
  const now = nowIso();
  const notes = extra.notes ?? null;
  const channel = extra.channel ?? null;
  const milestone = MILESTONE_COL[status];

  const existing = await db
    .prepare(`SELECT * FROM applications WHERE listing_id = ?`)
    .bind(listingId)
    .first();

  if (!existing) {
    const cols = ["listing_id", "status", "notes", "channel", "created_at", "updated_at"];
    const vals = [listingId, status, notes ?? "", channel, now, now];
    if (milestone) {
      cols.push(milestone);
      vals.push(now);
    }
    if (status === "sent") {
      if (!cols.includes("sent_at")) {
        cols.push("sent_at");
        vals.push(now);
      }
    }
    const placeholders = cols.map(() => "?").join(", ");
    await db
      .prepare(`INSERT INTO applications (${cols.join(", ")}) VALUES (${placeholders})`)
      .bind(...vals)
      .run();
    return;
  }

  const sets = ["status = ?", "updated_at = ?"];
  const binds = [status, now];
  if (notes !== null) {
    sets.push("notes = ?");
    binds.push(notes);
  }
  if (channel !== null) {
    sets.push("channel = ?");
    binds.push(channel);
  }
  if (milestone) {
    sets.push(`${milestone} = COALESCE(${milestone}, ?)`);
    binds.push(now);
  }
  if (status === "sent") {
    sets.push("sent_at = COALESCE(sent_at, ?)");
    binds.push(now);
  }
  binds.push(listingId);
  await db
    .prepare(`UPDATE applications SET ${sets.join(", ")} WHERE listing_id = ?`)
    .bind(...binds)
    .run();
}

async function getStatuses(db) {
  const statuses = {};
  const notes = {};
  const milestones = {};
  const likes = [];

  const apps = await db
    .prepare(
      `SELECT listing_id, status, notes, sent_at, replied_at, toured_at, rejected_at,
              skipped_at, updated_at
       FROM applications
       WHERE status != 'accepted'`
    )
    .all();
  for (const row of apps.results || []) {
    statuses[row.listing_id] = row.status;
    if (row.notes) notes[row.listing_id] = row.notes;
    milestones[row.listing_id] = {
      sentAt: row.sent_at || null,
      repliedAt: row.replied_at || null,
      touredAt: row.toured_at || null,
      rejectedAt: row.rejected_at || null,
      skippedAt: row.skipped_at || null,
      updatedAt: row.updated_at || null,
    };
  }

  const flags = await db
    .prepare(`SELECT listing_id, liked FROM listing_flags WHERE liked = 1`)
    .all();
  for (const row of flags.results || []) {
    likes.push(row.listing_id);
  }

  return { statuses, notes, milestones, likes };
}

async function setLiked(db, listingId, liked) {
  const now = nowIso();
  await db
    .prepare(
      `INSERT INTO listing_flags (listing_id, liked, is_scam_likely, updated_at)
       VALUES (?, ?, 0, ?)
       ON CONFLICT(listing_id) DO UPDATE SET
         liked = excluded.liked,
         updated_at = excluded.updated_at`
    )
    .bind(listingId, liked ? 1 : 0, now)
    .run();
  return liked;
}

async function getLiked(db, listingId) {
  const row = await db
    .prepare(`SELECT liked FROM listing_flags WHERE listing_id = ?`)
    .bind(listingId)
    .first();
  if (!row) return false;
  return Boolean(row.liked);
}

async function markScam(db, listingId) {
  await transitionApplication(db, listingId, "rejected");
  const now = nowIso();
  await db
    .prepare(
      `INSERT INTO listing_flags (listing_id, liked, is_scam_likely, updated_at)
       VALUES (?, 0, 1, ?)
       ON CONFLICT(listing_id) DO UPDATE SET
         is_scam_likely = 1,
         updated_at = excluded.updated_at`
    )
    .bind(listingId, now)
    .run();
}

async function revertListing(db, listingId) {
  await db.prepare(`DELETE FROM applications WHERE listing_id = ?`).bind(listingId).run();
  await db
    .prepare(
      `INSERT INTO listing_flags (listing_id, liked, is_scam_likely, updated_at)
       VALUES (?, 0, 0, ?)
       ON CONFLICT(listing_id) DO UPDATE SET
         is_scam_likely = 0,
         updated_at = excluded.updated_at`
    )
    .bind(listingId, nowIso())
    .run();
}

function scrapeOrigin(env) {
  const origin = String(env.APPLY_API_ORIGIN || "").trim().replace(/\/$/, "");
  return origin || null;
}

function healthEndpoints(env) {
  const endpoints = [...ENDPOINTS];
  if (scrapeOrigin(env)) {
    endpoints.push("scrape", "scrape/status");
  }
  return endpoints;
}

async function proxyToOrigin(request, env, path) {
  const origin = scrapeOrigin(env);
  if (!origin) {
    return jsonError(
      503,
      "Scrape needs your Mac API online — run scripts/workers.sh start && scripts/tunnel.sh"
    );
  }

  const headers = new Headers();
  const token = String(env.APPLY_API_TOKEN || "").trim();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const init = { method: request.method, headers };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
    const contentType = request.headers.get("Content-Type");
    if (contentType) {
      headers.set("Content-Type", contentType);
    }
  }

  let upstream;
  try {
    upstream = await fetch(`${origin}${path}`, init);
  } catch (err) {
    const message = err && err.message ? err.message : "upstream unreachable";
    return jsonError(502, `Scrape API unreachable (${message})`);
  }

  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

function geminiKey(env) {
  return String(env.GEMINI_API_KEY || env.GCP_KEY || env.GOOGLE_API_KEY || "").trim();
}

function compactListing(item) {
  const details = String(item?.details || item?.description || "").trim().slice(0, 280);
  return {
    id: String(item?.id || ""),
    title: String(item?.title || "").slice(0, 120),
    price: item?.price ?? null,
    neighborhood: String(item?.neighborhood || item?.displayAddress || "").slice(0, 80),
    address: String(item?.displayAddress || item?.rentalAddress || "").slice(0, 80),
    layout: String(item?.layoutLabel || ""),
    bath: String(item?.bathPrivacy || ""),
    sqft: String(item?.sqftLabel || ""),
    moveIn: String(item?.moveInLabel || ""),
    source: String(item?.source || ""),
    score: item?.score ?? null,
    poster: String(item?.posterName || ""),
    roomsInHouse: Number(item?.roomsInHouse || item?.roomsListed || 1) || 1,
    details,
  };
}

async function callGeminiFind(env, question, listings) {
  const key = geminiKey(env);
  if (!key) {
    throw new Error("Gemini API key is not configured");
  }
  const prompt =
    "Filter this housing-search queue. Use ONLY the listings JSON below. " +
    "Do not use the web or outside knowledge. Do not invent listings.\n\n" +
    `QUESTION:\n${question}\n\nLISTINGS:\n${JSON.stringify(listings)}\n\n` +
    "Return JSON only:\n" +
    '{ "ids": ["listing-id", ...], "note": "one short sentence" }\n' +
    "Include every listing that matches. If a house has 2+ rooms available " +
    "(roomsInHouse >= 2, or details/author say multiple rooms), treat those " +
    "as the same house when the question asks about multiple rooms. " +
    'If nothing matches, return {"ids": [], "note": "No matching listings."}.';

  let lastError = "Gemini find failed";
  for (const model of GEMINI_MODELS) {
    const url =
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(key)}`;
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.1, responseMimeType: "application/json" },
        }),
      });
      if (!response.ok) {
        lastError = `${model} HTTP ${response.status}`;
        continue;
      }
      const payload = await response.json();
      const parts = payload?.candidates?.[0]?.content?.parts || [];
      const text = parts.map((part) => String(part?.text || "")).join("").trim();
      if (!text) {
        lastError = `${model} empty response`;
        continue;
      }
      const cleaned = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
      return JSON.parse(cleaned);
    } catch (err) {
      lastError = err && err.message ? err.message : String(err);
    }
  }
  throw new Error(lastError);
}

async function handleFind(request, env) {
  const body = await readJson(request);
  const question = String(body.question || body.q || "").trim();
  if (!question) {
    return jsonError(400, "Type a question first");
  }
  const incoming = Array.isArray(body.listings) ? body.listings : [];
  const known = new Set();
  const listings = [];
  for (const item of incoming.slice(0, 220)) {
    const row = compactListing(item);
    if (!row.id || known.has(row.id)) continue;
    known.add(row.id);
    listings.push(row);
  }
  if (!listings.length) {
    return jsonResponse({ ok: true, ids: [], note: "No listings loaded." });
  }
  try {
    const parsed = await callGeminiFind(env, question.slice(0, 400), listings);
    const rawIds = Array.isArray(parsed?.ids) ? parsed.ids : [];
    const ids = rawIds.map((id) => String(id)).filter((id) => known.has(id));
    const note = String(parsed?.note || "").trim() ||
      (ids.length ? `${ids.length} matching listing(s).` : "No matching listings.");
    return jsonResponse({ ok: true, ids, note: note.slice(0, 240) });
  } catch (err) {
    const message = err && err.message ? err.message : "Gemini find failed";
    return jsonError(502, message);
  }
}

export async function handleQueueApi(request, env, segments, method) {
  const route = segments.join("/");
  if (method === "POST" && route === "find") {
    return handleFind(request, env);
  }

  const db = env.DB;
  if (!db) {
    return jsonError(503, "D1 database not configured");
  }

  if (method === "GET" && route === "health") {
    return jsonResponse({
      ok: true,
      gmail: false,
      message: "Apply API ready (Cloudflare D1)",
      endpoints: healthEndpoints(env),
      scrapeAvailable: Boolean(scrapeOrigin(env)),
      findAvailable: Boolean(geminiKey(env)),
    });
  }

  if (method === "GET" && route === "statuses") {
    const payload = await getStatuses(db);
    return jsonResponse({ ok: true, ...payload });
  }

  if (method === "GET" && route === "scrape/status") {
    return proxyToOrigin(request, env, "/api/scrape/status");
  }

  if (method === "POST" && route === "scrape") {
    return proxyToOrigin(request, env, "/api/scrape");
  }

  if (method !== "POST") {
    return jsonError(404, "Not found");
  }

  const actionMatch = route.match(
    /^(sent|replied|skip|like|delete|scam|revert|notes|toured|accepted)\/([^/]+)$/
  );
  if (!actionMatch) {
    return jsonError(404, "Not found");
  }

  const [, action, listingId] = actionMatch;
  if (!validId(listingId)) {
    return jsonError(400, "Invalid listing id");
  }

  switch (action) {
    case "sent": {
      await transitionApplication(db, listingId, "sent", { channel: "craigslist" });
      return jsonResponse({ ok: true, status: "sent", channel: "craigslist" });
    }
    case "replied": {
      await transitionApplication(db, listingId, "replied");
      return jsonResponse({ ok: true, status: "replied" });
    }
    case "skip": {
      await transitionApplication(db, listingId, "skipped");
      return jsonResponse({ ok: true, status: "skipped" });
    }
    case "delete": {
      await transitionApplication(db, listingId, "rejected");
      return jsonResponse({ ok: true, status: "rejected" });
    }
    case "scam": {
      await markScam(db, listingId);
      return jsonResponse({ ok: true, status: "rejected", is_scam_likely: true });
    }
    case "revert": {
      await revertListing(db, listingId);
      return jsonResponse({ ok: true, status: "draft", is_scam_likely: false });
    }
    case "toured": {
      await transitionApplication(db, listingId, "toured");
      return jsonResponse({ ok: true, status: "toured" });
    }
    case "accepted": {
      await transitionApplication(db, listingId, "accepted");
      return jsonResponse({ ok: true, status: "accepted" });
    }
    case "notes": {
      const body = await readJson(request);
      const notesText = String(body.notes || "").trim();
      const existing = await db
        .prepare(`SELECT 1 FROM applications WHERE listing_id = ?`)
        .bind(listingId)
        .first();
      if (existing) {
        await db
          .prepare(`UPDATE applications SET notes = ?, updated_at = ? WHERE listing_id = ?`)
          .bind(notesText, nowIso(), listingId)
          .run();
      } else {
        const now = nowIso();
        await db
          .prepare(
            `INSERT INTO applications (listing_id, status, notes, channel, created_at, updated_at)
             VALUES (?, 'draft', ?, NULL, ?, ?)`
          )
          .bind(listingId, notesText, now, now)
          .run();
      }
      return jsonResponse({ ok: true, notes: notesText });
    }
    case "like": {
      const body = await readJson(request);
      let liked;
      if (body.liked === undefined || body.liked === null) {
        liked = !(await getLiked(db, listingId));
      } else {
        liked = Boolean(body.liked);
      }
      await setLiked(db, listingId, liked);
      return jsonResponse({ ok: true, liked });
    }
    default:
      return jsonError(404, "Not found");
  }
}
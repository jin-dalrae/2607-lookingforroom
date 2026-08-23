/** Instant local Find over loaded listings — no network. */
(function (root) {
  const HOODS = [
    "hayes valley", "north beach", "telegraph hill", "russian hill",
    "pacific heights", "lower pacific heights", "financial district",
    "civic center", "union square", "lower nob hill", "nob hill",
    "alamo square", "western addition", "lower haight", "upper haight",
    "haight ashbury", "haight-ashbury", "cole valley", "duboce triangle",
    "potrero hill", "mission bay", "south beach", "south of market",
    "mission district", "inner mission", "mission dolores", "bernal heights",
    "noe valley", "upper market", "fisherman's wharf", "jackson square",
    "yerba buena", "rincon hill", "china basin", "showplace square",
    "visitacion valley", "hunter's point", "hunters point", "silver terrace",
    "presidio heights", "laurel heights", "inner richmond", "outer richmond",
    "inner sunset", "outer sunset", "golden gate heights", "west portal",
    "forest hill", "glen park", "diamond heights", "twin peaks",
    "corona heights", "ashbury heights", "anza vista", "cathedral hill",
    "polk gulch", "fort mason", "treasure island", "cow hollow",
    "design district", "valencia corridor", "dolores park",
    "chinatown", "tenderloin", "japantown", "fillmore", "panhandle",
    "dogpatch", "embarcadero", "marina", "castro", "mission", "soma",
    "nopa", "haight", "potrero", "bernal", "bayview", "excelsior",
    "ingleside", "richmond", "sunset", "downtown", "fidi",
  ].sort((a, b) => b.length - a.length);

  const STOP = new Set([
    "a", "an", "the", "in", "on", "at", "of", "for", "to", "and", "or",
    "with", "near", "around", "from", "that", "this", "these", "those",
    "me", "my", "i", "we", "show", "find", "list", "listings", "listing",
    "house", "houses", "home", "homes", "place", "places", "room", "rooms",
    "apartment", "apt", "unit", "want", "looking", "need", "please",
    "available", "are", "is", "be", "can", "any", "some", "one",
  ]);

  function parseFindQuery(question) {
    let text = String(question || "").toLowerCase();
    text = text.replace(/[“”]/g, '"').replace(/[’]/g, "'");
    const parsed = {
      maxPrice: null,
      minPrice: null,
      bath: null,
      layouts: [],
      multiRoom: false,
      source: null,
      liked: false,
      hoods: [],
      terms: [],
    };

    const under = text.match(/(?:under|below|max|less than|up to|no more than|<=)\s*\$?\s*(\d{3,5})/);
    const dollar = text.match(/\$\s*(\d{3,5})/);
    if (under) parsed.maxPrice = Number(under[1]);
    else if (dollar) parsed.maxPrice = Number(dollar[1]);
    const over = text.match(/(?:over|above|at least|min(?:imum)?|>=)\s*\$?\s*(\d{3,5})/);
    if (over) parsed.minPrice = Number(over[1]);

    if (/\b(private|own|en[- ]?suite)\s+(bath|bathroom|ba)\b|\bensuite\b|\bprivate bath\b/.test(text)) {
      parsed.bath = "private";
    } else if (/\bshared\s+(bath|bathroom|ba)\b/.test(text)) {
      parsed.bath = "shared";
    }

    if (
      /\b(?:2\+|two or more|more than (?:1|one)|multiple)\s+rooms?\b/.test(text) ||
      /\b(?:two|2)\s+rooms?\s+(?:in|from|for)\b/.test(text) ||
      /\brooms?\s+in\s+(?:the\s+)?(?:same\s+)?(?:house|apartment|flat|unit)\b/.test(text) ||
      /\bsame house\b/.test(text) ||
      /\b2\+\s*rooms?\b/.test(text)
    ) {
      parsed.multiRoom = true;
    }

    if (/\b(1r1b|1\s*bed(?:room)?(?:\s*1\s*bath)?|1br|1\s*br\s*1\s*ba|studio)\b/.test(text)) {
      parsed.layouts.push("1r1b", "studio", "1br");
    }
    if (/\b(2r2b|2\s*bed(?:room)?|2br|2\s*br\s*2\s*ba)\b/.test(text)) {
      parsed.layouts.push("2r2b", "2br");
    }
    if (/\b(3r2b|3r3b|3\s*bed(?:room)?|3br)\b/.test(text)) {
      parsed.layouts.push("3r2b", "3r3b", "3br");
    }

    if (/\bfacebook\b|\bfb\b/.test(text)) parsed.source = "facebook";
    else if (/\bzillow\b/.test(text)) parsed.source = "zillow";
    else if (/\bcraigslist\b|\bcl\b/.test(text)) parsed.source = "craigslist";

    if (/\bliked\b|\bstarred\b|\bfavorites?\b/.test(text)) parsed.liked = true;

    let leftover = text;
    leftover = leftover.replace(/(?:under|below|max|less than|up to|over|above|at least|min(?:imum)?)\s*\$?\s*\d{3,5}/g, " ");
    leftover = leftover.replace(/\$\s*\d{3,5}/g, " ");
    leftover = leftover.replace(/\b(private|own|en[- ]?suite|shared)\s+(bath|bathroom|ba)\b/g, " ");
    leftover = leftover.replace(/\b(ensuite|private bath)\b/g, " ");
    leftover = leftover.replace(/\b(facebook|zillow|craigslist|\bfb\b|\bcl\b)\b/g, " ");
    leftover = leftover.replace(/\b(1r1b|2r2b|3r2b|3r3b|1br|2br|3br|studio)\b/g, " ");
    leftover = leftover.replace(/\b(two or more|more than one|multiple rooms|same house|2\+ rooms?)\b/g, " ");
    leftover = leftover.replace(/\b(two|2)\s+rooms?\b/g, " ");

    for (const hood of HOODS) {
      if (leftover.includes(hood)) {
        parsed.hoods.push(hood);
        leftover = leftover.split(hood).join(" ");
      }
    }

    parsed.terms = leftover
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((w) => w.length >= 3 && !STOP.has(w));

    return parsed;
  }

  function describeParse(parsed) {
    const bits = [];
    if (parsed.hoods.length) bits.push(parsed.hoods.join(" / "));
    if (parsed.maxPrice) bits.push("≤$" + parsed.maxPrice);
    if (parsed.minPrice) bits.push("≥$" + parsed.minPrice);
    if (parsed.bath === "private") bits.push("private bath");
    if (parsed.bath === "shared") bits.push("shared bath");
    if (parsed.multiRoom) bits.push("2+ rooms in house");
    if (parsed.layouts.length) bits.push(parsed.layouts[0]);
    if (parsed.source) bits.push(parsed.source);
    if (parsed.liked) bits.push("liked");
    if (parsed.terms.length) bits.push(parsed.terms.join(" "));
    return bits.join(" · ");
  }

  function listingBlob(item) {
    return [
      item.title,
      item.neighborhood,
      item.displayAddress,
      item.rentalAddress,
      item.city,
      item.layoutLabel,
      item.bathPrivacy,
      item.sqftLabel,
      item.moveInLabel,
      item.posterName,
      item.details,
      item.source,
      item.notes,
    ].filter(Boolean).join(" ").toLowerCase();
  }

  function listingMatches(item, parsed) {
    const price = Number(item.price);
    if (parsed.maxPrice != null) {
      if (!Number.isFinite(price) || price > parsed.maxPrice) return false;
    }
    if (parsed.minPrice != null) {
      if (!Number.isFinite(price) || price < parsed.minPrice) return false;
    }
    if (parsed.bath && String(item.bathPrivacy || "unknown") !== parsed.bath) return false;
    if (parsed.multiRoom && !item.isMultiRoomHouse) return false;
    if (parsed.source && item.source !== parsed.source) return false;
    if (parsed.liked && !item.liked) return false;
    if (parsed.layouts.length) {
      const layout = String(item.layoutLabel || "").toLowerCase();
      const blob = listingBlob(item);
      const hit = parsed.layouts.some((label) => layout.includes(label) || blob.includes(label));
      if (!hit) return false;
    }
    if (parsed.hoods.length) {
      const blob = listingBlob(item);
      if (!parsed.hoods.some((hood) => blob.includes(hood))) return false;
    }
    if (parsed.terms.length) {
      const blob = listingBlob(item);
      const hits = parsed.terms.filter((term) => blob.includes(term)).length;
      if (parsed.terms.length <= 2) {
        if (hits < parsed.terms.length) return false;
      } else if (hits < Math.ceil(parsed.terms.length * 0.7)) {
        return false;
      }
    }
    return true;
  }

  function findListings(question, listings) {
    const query = String(question || "").trim();
    if (!query) {
      return { ids: [], note: "", parsed: null };
    }
    const parsed = parseFindQuery(query);
    const hasConstraint =
      parsed.maxPrice || parsed.minPrice || parsed.bath || parsed.multiRoom ||
      parsed.source || parsed.liked || parsed.layouts.length ||
      parsed.hoods.length || parsed.terms.length;
    if (!hasConstraint) {
      return { ids: [], note: "Try a neighborhood, price, bathroom, or keyword.", parsed };
    }
    const ids = [];
    for (const item of listings || []) {
      if (item && listingMatches(item, parsed)) ids.push(String(item.id));
    }
    const summary = describeParse(parsed);
    const note = ids.length
      ? `${ids.length} match${ids.length === 1 ? "" : "es"} · ${summary}`
      : `No matches · ${summary}`;
    return { ids, note, parsed };
  }

  root.LfrFind = { parseFindQuery, findListings, listingMatches };
})(typeof window !== "undefined" ? window : globalThis);

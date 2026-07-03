const LOGIN_PATH = "/__auth/login";

async function authToken(password) {
  const data = new TextEncoder().encode(`${password}:site-auth`);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function parseCookies(header) {
  const cookies = {};
  if (!header) return cookies;
  for (const part of header.split(";")) {
    const [key, ...value] = part.trim().split("=");
    if (key) cookies[key] = value.join("=");
  }
  return cookies;
}

function loginHtml(error = "") {
  const errorBlock = error
    ? `<p class="error" role="alert">${error}</p>`
    : "";
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in</title>
  <style>
    :root {
      --bg: #f5f5f7;
      --card: #fff;
      --text: #1d1d1f;
      --muted: #6e6e73;
      --blue: #0071e3;
      --border: #d2d2d7;
      --red: #d70015;
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
      background: var(--bg);
      color: var(--text);
    }
    main {
      width: min(360px, 100%);
      background: var(--card);
      border-radius: 16px;
      padding: 2rem;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
    }
    h1 { margin: 0 0 0.35rem; font-size: 1.35rem; }
    p { margin: 0 0 1.25rem; color: var(--muted); }
    label { display: block; font-size: 0.9rem; margin-bottom: 0.4rem; }
    input {
      width: 100%;
      padding: 0.75rem 0.85rem;
      border: 1px solid var(--border);
      border-radius: 10px;
      font-size: 1rem;
      margin-bottom: 1rem;
    }
    button {
      width: 100%;
      padding: 0.8rem 1rem;
      border: 0;
      border-radius: 10px;
      background: var(--blue);
      color: #fff;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
    }
    button:hover { filter: brightness(1.05); }
    .error {
      color: var(--red);
      font-size: 0.9rem;
      margin: -0.5rem 0 1rem;
    }
  </style>
</head>
<body>
  <main>
    <h1>SF Room Finder</h1>
    <p>Enter the site password to continue.</p>
    ${errorBlock}
    <form method="post" action="${LOGIN_PATH}">
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
      <button type="submit">Continue</button>
    </form>
  </main>
</body>
</html>`;
}

function safeRedirect(value) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/";
  }
  return value;
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);
  const password = env.SITE_PASSWORD || "9809";

  if (url.pathname === LOGIN_PATH) {
    if (request.method === "POST") {
      const form = await request.formData();
      const submitted = String(form.get("password") || "");
      if (submitted === password) {
        const token = await authToken(password);
        const redirect = safeRedirect(url.searchParams.get("redirect"));
        return new Response(null, {
          status: 302,
          headers: {
            Location: redirect,
            "Set-Cookie": `site_auth=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`,
          },
        });
      }
      return new Response(loginHtml("Wrong password. Try again."), {
        status: 401,
        headers: { "Content-Type": "text/html;charset=UTF-8" },
      });
    }

    return new Response(loginHtml(), {
      headers: { "Content-Type": "text/html;charset=UTF-8" },
    });
  }

  const cookies = parseCookies(request.headers.get("Cookie"));
  const expected = await authToken(password);
  if (cookies.site_auth === expected) {
    return next();
  }

  const redirect = encodeURIComponent(url.pathname + url.search);
  return new Response(null, {
    status: 302,
    headers: { Location: `${LOGIN_PATH}?redirect=${redirect}` },
  });
}
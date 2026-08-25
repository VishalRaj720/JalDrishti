/**
 * Serves the portal as static assets, and proxies /api/* to the API on Render.
 *
 * WHY A WORKER AND NOT `_redirects`. The portal calls `/api/v1/...` as a
 * same-origin RELATIVE path -- no fetch in the codebase names a host -- so
 * something has to join the static bundle to the API under one hostname.
 * On Cloudflare Pages that was one line in `_redirects`. Cloudflare's Workers
 * static-asset router parses `_redirects` too, but it "will only support
 * relative URLs on your site and you cannot proxy external domains", so the
 * rewrite to onrender.com is exactly the case it refuses. This file is that
 * line, expressed as code.
 *
 * `run_worker_first: ["/api/*"]` in wrangler.jsonc is what gets us here at all:
 * without it the asset router answers first and `not_found_handling:
 * single-page-application` would hand back index.html for /api/* -- every API
 * call returning 200 and a page of HTML, which is a far more confusing failure
 * than a 404.
 */

const API_ORIGIN = "https://jaldrishti-api.onrender.com";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/")) {
      const target = new URL(url.pathname + url.search, API_ORIGIN);

      // Copy the headers explicitly. Note we do NOT build this as
      // `new Request(target, {...request, headers})` -- a Request's properties
      // are not enumerable own properties, so the spread yields an empty object
      // and every header, the method and the body are silently dropped.
      const headers = new Headers(request.headers);

      // THE RATE LIMITER DEPENDS ON THIS. slowapi keys anonymous callers by IP,
      // and uvicorn runs with `--proxy-headers`, which reads X-Forwarded-For.
      // From inside a Worker the client address arrives as CF-Connecting-IP;
      // if we do not translate it, every anonymous request in the world
      // presents as the same address and shares ONE bucket -- so ten bad
      // logins from anywhere would lock out every citizen at once. That matters
      // here specifically because the four demo passwords are published on
      // purpose, which makes /auth/login the busiest guessed surface we have.
      const clientIp = request.headers.get("CF-Connecting-IP");
      if (clientIp) {
        headers.set("X-Forwarded-For", clientIp);
        headers.set("X-Forwarded-Proto", "https");
      }
      // Host must belong to the ORIGIN, not to the portal, or Render routes it
      // nowhere. Deleting it lets fetch() set it from the target URL.
      headers.delete("host");

      const hasBody = request.method !== "GET" && request.method !== "HEAD";
      return fetch(target, {
        method: request.method,
        headers,
        body: hasBody ? request.body : undefined,
        // Let the caller see the API's own 3xx rather than following it here.
        redirect: "manual",
      });
    }

    // Everything else is the built SPA. The asset router handles index.html
    // fallback via not_found_handling, so this only runs if /api/* did not
    // match and run_worker_first still routed here.
    return env.ASSETS.fetch(request);
  },
};

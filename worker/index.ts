import searchIndex from "./generated/search-index.json";
import { SNAPSHOT } from "./generated/snapshot";
import { createSearch, type SearchProduct } from "./search";

interface Env { ASSETS: { fetch(request: Request): Promise<Response> } }
const DISCLAIMER = "Unofficial independent project. Food-'O'-Copoeia is a ready reference; original FSS regulations, Gazette publications, and FSSAI directions prevail.";
const CORS = { "access-control-allow-origin": "*", "access-control-allow-methods": "GET, OPTIONS", "access-control-allow-headers": "content-type" };
const searchProducts = createSearch(searchIndex as SearchProduct[]);

function json(value: unknown, status = 200, cache = "public, max-age=300"): Response {
  return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": cache, ...CORS } });
}

async function staticJson(env: Env, request: Request, path: string): Promise<Response> {
  const url = new URL(path, request.url);
  const response = await env.ASSETS.fetch(new Request(url, request));
  const headers = new Headers(response.headers);
  Object.entries(CORS).forEach(([key, value]) => headers.set(key, value));
  headers.set("cache-control", "public, max-age=300");
  return new Response(response.body, { status: response.status, headers });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (request.method !== "GET") return json({ error: "method_not_allowed" }, 405);
    const url = new URL(request.url);
    if (url.pathname === "/product/") {
      const identity = url.searchParams.get("id");
      if (identity && /^\d+$/.test(identity)) return Response.redirect(new URL(`/products/${identity}/`, url), 301);
    }
    if (url.pathname === "/api/v1/meta") return staticJson(env, request, "/data/manifest.json");
    if (url.pathname === "/api/v1/search") {
      const query = url.searchParams.get("q") ?? "";
      if (query.trim().length < 2 || query.length > 100) return json({ error: "invalid_query", message: "q must contain 2 to 100 characters" }, 400);
      const requested = Number.parseInt(url.searchParams.get("limit") ?? "20", 10);
      const limit = Number.isFinite(requested) ? Math.max(1, Math.min(50, requested)) : 20;
      const results = searchProducts(query, limit);
      return json({ unofficial: true, snapshot: SNAPSHOT, disclaimer: DISCLAIMER, query, count: results.length, results });
    }
    const product = url.pathname.match(/^\/api\/v1\/products\/(\d+)$/);
    if (product) return staticJson(env, request, `/data/v${SNAPSHOT}/products/${product[1]}.json`);
    if (url.pathname.startsWith("/api/")) return json({ error: "not_found" }, 404);
    if (url.pathname.startsWith("/downloads/latest/")) return env.ASSETS.fetch(request);
    return env.ASSETS.fetch(request);
  },
};

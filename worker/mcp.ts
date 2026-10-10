import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { CfWorkerJsonSchemaValidator } from "@modelcontextprotocol/sdk/validation/cfworker";
import * as z from "zod/v4";
import { SNAPSHOT } from "./generated/snapshot";
import type { SearchResult } from "./search";

interface AssetsBinding {
  fetch(request: Request): Promise<Response>;
}

export interface McpEnv {
  ASSETS: AssetsBinding;
}

type SearchProducts = (query: string, limit?: number) => SearchResult[];

const ENDPOINT_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "POST, OPTIONS",
  "access-control-allow-headers": "content-type, accept, mcp-protocol-version",
};

function result(value: Record<string, unknown>) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(value) }],
    structuredContent: value,
  };
}

async function readAssetJson(env: McpEnv, request: Request, path: string): Promise<Record<string, unknown> | null> {
  const response = await env.ASSETS.fetch(new Request(new URL(path, request.url)));
  if (!response.ok) return null;
  return await response.json() as Record<string, unknown>;
}

function createServer(env: McpEnv, request: Request, searchProducts: SearchProducts): McpServer {
  const server = new McpServer(
    { name: "open-foodocopoeia", title: "Open Food-'O'-Copoeia", version: "1.0.0" },
    { jsonSchemaValidator: new CfWorkerJsonSchemaValidator() },
  );

  server.registerTool("search_food_products", {
    title: "Search food products",
    description: "Search FSSAI Food-'O'-Copoeia products using weighted, prefix, multi-word, and fuzzy matching.",
    inputSchema: {
      query: z.string().min(1).max(100).describe("Product name or search terms"),
      limit: z.number().int().min(1).max(50).optional().describe("Maximum results; defaults to 20"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }, async ({ query, limit }) => {
    const results = searchProducts(query, limit ?? 20);
    return result({ query, count: results.length, results });
  });

  server.registerTool("get_food_product", {
    title: "Get a food product",
    description: "Get one product's hierarchy, quality parameters, test methods, and source provenance by numeric identity.",
    inputSchema: {
      product_id: z.string().regex(/^\d+$/).describe("Numeric product identity, for example 48 for Rice"),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }, async ({ product_id }) => {
    const product = await readAssetJson(env, request, `/data/v${SNAPSHOT}/products/${product_id}.json`);
    if (!product) return { content: [{ type: "text", text: `Product ${product_id} was not found.` }], isError: true };
    return result(product);
  });

  server.registerTool("get_dataset_metadata", {
    title: "Get dataset metadata",
    description: "Get the current snapshot version, record counts, checksums, retrieval range, and legal disclaimer.",
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }, async () => {
    const metadata = await readAssetJson(env, request, "/data/manifest.json");
    if (!metadata) return { content: [{ type: "text", text: "Dataset metadata is unavailable." }], isError: true };
    return result(metadata);
  });

  return server;
}

function methodNotAllowed(): Response {
  return Response.json(
    { jsonrpc: "2.0", error: { code: -32000, message: "Method not allowed." }, id: null },
    { status: 405, headers: { Allow: "POST", ...ENDPOINT_HEADERS } },
  );
}

export async function handleMcp(request: Request, env: McpEnv, searchProducts: SearchProducts): Promise<Response> {
  if (request.method !== "POST") return methodNotAllowed();
  const server = createServer(env, request, searchProducts);
  const transport = new WebStandardStreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  await server.connect(transport);
  const response = await transport.handleRequest(request);
  const headers = new Headers(response.headers);
  Object.entries(ENDPOINT_HEADERS).forEach(([name, value]) => headers.set(name, value));
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

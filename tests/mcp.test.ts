import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { join } from "node:path";
import searchIndex from "../worker/generated/search-index.json";
import { handleMcp, type McpEnv } from "../worker/mcp";
import { createSearch, type SearchProduct } from "../worker/search";

const searchProducts = createSearch(searchIndex as SearchProduct[]);
const env: McpEnv = {
  ASSETS: {
    async fetch(request: Request): Promise<Response> {
      try {
        const path = new URL(request.url).pathname.replace(/^\//, "");
        const body = await readFile(join(process.cwd(), "public", path));
        return new Response(body, { headers: { "content-type": "application/json" } });
      } catch {
        return new Response("Not found", { status: 404 });
      }
    },
  },
};

async function rpc(method: string, params: Record<string, unknown> = {}, id = 1) {
  const request = new Request("https://open-foodocopoeia.thakerinnovations.com/mcp", {
    method: "POST",
    headers: {
      accept: "application/json, text/event-stream",
      "content-type": "application/json",
      "mcp-protocol-version": "2025-11-25",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
  });
  const response = await handleMcp(request, env, searchProducts);
  return { response, body: await response.json() as any };
}

test("MCP initializes as a stateless Streamable HTTP server", async () => {
  const { response, body } = await rpc("initialize", {
    protocolVersion: "2025-11-25", capabilities: {}, clientInfo: { name: "test", version: "1" },
  });
  assert.equal(response.status, 200);
  assert.equal(body.result.serverInfo.name, "open-foodocopoeia");
  assert.equal(body.result.protocolVersion, "2025-11-25");
  assert.ok(body.result.capabilities.tools);
});

test("MCP lists the public read-only tools", async () => {
  const { body } = await rpc("tools/list");
  assert.deepEqual(body.result.tools.map((tool: any) => tool.name), [
    "search_food_products", "get_food_product", "get_dataset_metadata",
  ]);
  assert.ok(body.result.tools.every((tool: any) => tool.annotations.readOnlyHint));
});

test("MCP search and product tools return structured data", async () => {
  const search = await rpc("tools/call", { name: "search_food_products", arguments: { query: "Others Oil", limit: 2 } });
  assert.equal(search.body.result.structuredContent.results[0].id, "561");

  const product = await rpc("tools/call", { name: "get_food_product", arguments: { product_id: "48" } });
  assert.ok(product.body.result.structuredContent, JSON.stringify(product.body));
  assert.equal(product.body.result.structuredContent.product.name, "Rice");
  assert.equal(product.body.result.structuredContent.product.quality_parameters.length, 40);

  const milk = await rpc("tools/call", { name: "get_food_product", arguments: { product_id: "266" } });
  assert.equal(milk.body.result.structuredContent.product.microbiological_requirements.length, 10);
  assert.equal(milk.body.result.structuredContent.product.microbiological_requirements[0].parameter, "Aerobic Plate Count");

  const oil = await rpc("tools/call", { name: "get_food_product", arguments: { product_id: "72" } });
  assert.equal(oil.body.result.structuredContent.product.pesticide_residue_requirements[0].analyte_or_requirement, "Phenthoate");
  assert.equal(oil.body.result.structuredContent.product.heavy_metal_requirements[0].analyte_or_requirement, "Lead");

  const metadata = await rpc("tools/call", { name: "get_dataset_metadata", arguments: {} });
  assert.equal(metadata.body.result.structuredContent.counts.microbiological_requirements, 1809);
  assert.equal(metadata.body.result.structuredContent.counts.pesticide_residue_requirements, 4044);
  assert.equal(metadata.body.result.structuredContent.counts.heavy_metal_requirements, 2729);
});

test("MCP standalone GET is not offered for the stateless server", async () => {
  const response = await handleMcp(new Request("https://open-foodocopoeia.thakerinnovations.com/mcp"), env, searchProducts);
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "POST");
});

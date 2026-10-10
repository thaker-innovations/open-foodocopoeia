import assert from "node:assert/strict";
import test from "node:test";
import { normalize, search, type SearchProduct } from "../worker/search";

const products: SearchProduct[] = [
  { id: "48", name: "Rice", category: "Cereals", subcategory: "Rice", specific_subcategory: "N/A" },
  { id: "576", name: "Basmati Rice", category: "Cereals", subcategory: "Rice", specific_subcategory: "Basmati Rice" },
  { id: "34", name: "Coconut Oil", category: "Fats and oils", subcategory: "Vegetable oils", specific_subcategory: "Coconut Oil" },
];

test("normalizes punctuation and case", () => assert.equal(normalize("  Basmati—RICE "), "basmati rice"));
test("prefix query ric finds Rice first", () => {
  const results = search(products, "ric");
  assert.equal(results[0].id, "48");
  assert.equal(results[0].match, "name_prefix");
  assert.equal(results[1].id, "576");
});
test("fuzzy typo finds coconut", () => assert.equal(search(products, "cocnut")[0].id, "34"));
test("rejects one-character query locally", () => assert.deepEqual(search(products, "r"), []));

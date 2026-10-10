import assert from "node:assert/strict";
import test from "node:test";
import searchIndex from "../worker/generated/search-index.json";
import { normalize, search, type SearchProduct } from "../worker/search";

const products: SearchProduct[] = [
  { id: "48", name: "Rice", category: "Cereals", subcategory: "Rice", specific_subcategory: "N/A" },
  { id: "576", name: "Basmati Rice", category: "Cereals", subcategory: "Rice", specific_subcategory: "Basmati Rice" },
  { id: "34", name: "Coconut Oil", category: "Fats and oils", subcategory: "Vegetable oils", specific_subcategory: "Coconut Oil" },
  { id: "99", name: "Others — Solvent Extracted Crude Vegetable Oils", category: "Fats, oils and fat emulsions", subcategory: "Vegetable oils", specific_subcategory: "Other oils" },
];

test("normalizes punctuation and case", () => assert.equal(normalize("  Basmati—RICE "), "basmati rice"));
test("prefix query ric finds Rice first", () => {
  const results = search(products, "ric");
  assert.equal(results[0].id, "48");
  assert.equal(results[0].match, "name_prefix");
  assert.equal(results[1].id, "576");
});
test("fuzzy typo finds coconut", () => assert.equal(search(products, "cocnut")[0].id, "34"));
test("matches unordered terms across a product name", () => {
  assert.equal(search(products, "others oil")[0].id, "99");
});
test("supports instant one-character search", () => assert.equal(search(products, "r")[0].id, "48"));
test("finds the real Others vegetable oils entry", () => {
  assert.equal(search(searchIndex as SearchProduct[], "Others Oil")[0].id, "561");
});

import MiniSearch from "minisearch";

export interface SearchProduct {
  id: string;
  name: string;
  category: string | null;
  subcategory: string | null;
  specific_subcategory: string | null;
}

export interface SearchResult extends SearchProduct {
  score: number;
  match: "exact" | "name_prefix" | "token_prefix" | "substring" | "fuzzy";
}

export function normalize(value: string): string {
  return value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("en").replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
}

function matchType(product: SearchProduct, rawQuery: string): SearchResult["match"] {
  const query = normalize(rawQuery);
  const name = normalize(product.name);
  if (name === query) return "exact";
  if (name.startsWith(query)) return "name_prefix";
  const hierarchy = normalize([product.name, product.specific_subcategory, product.subcategory, product.category]
    .filter(Boolean).join(" "));
  const tokens = hierarchy.split(" ");
  const queryTokens = query.split(" ");
  if (queryTokens.every(term => tokens.some(token => token.startsWith(term)))) return "token_prefix";
  if (hierarchy.includes(query)) return "substring";
  return "fuzzy";
}

export function createSearch(products: SearchProduct[]): (rawQuery: string, limit?: number) => SearchResult[] {
  const index = new MiniSearch<SearchProduct>({
    fields: ["name", "specific_subcategory", "subcategory", "category"],
    storeFields: ["name", "category", "subcategory", "specific_subcategory"],
    searchOptions: {
      boost: { name: 5, specific_subcategory: 4, subcategory: 2.5, category: 1 },
      combineWith: "AND",
      prefix: true,
      fuzzy: term => term.length >= 4 ? 0.2 : false,
      maxFuzzy: 2,
      weights: { prefix: 0.8, fuzzy: 0.55 },
    },
  });
  index.addAll(products);

  return (rawQuery: string, limit = 20): SearchResult[] => {
    const query = normalize(rawQuery);
    if (!query) return [];
    const priority: Record<SearchResult["match"], number> = {
      exact: 5, name_prefix: 4, token_prefix: 3, substring: 2, fuzzy: 1,
    };
    return index.search(query).map(result => {
      const product: SearchProduct = {
        id: String(result.id),
        name: result.name,
        category: result.category ?? null,
        subcategory: result.subcategory ?? null,
        specific_subcategory: result.specific_subcategory ?? null,
      };
      const match = matchType(product, query);
      return { ...product, score: result.score + priority[match] * 1_000, match };
    }).sort((a, b) => b.score - a.score || a.name.localeCompare(b.name) || Number(a.id) - Number(b.id))
      .slice(0, Math.max(1, Math.min(50, limit)));
  };
}

export function search(products: SearchProduct[], rawQuery: string, limit = 20): SearchResult[] {
  return createSearch(products)(rawQuery, limit);
}

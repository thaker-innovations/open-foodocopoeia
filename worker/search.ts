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

function distance(a: string, b: string, maximum: number): number {
  if (Math.abs(a.length - b.length) > maximum) return maximum + 1;
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    let rowMinimum = i;
    for (let j = 1; j <= b.length; j++) {
      const value = Math.min(current[j - 1] + 1, previous[j] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      current.push(value); rowMinimum = Math.min(rowMinimum, value);
    }
    if (rowMinimum > maximum) return maximum + 1;
    previous = current;
  }
  return previous[b.length];
}

function rank(product: SearchProduct, query: string): Pick<SearchResult, "score" | "match"> | null {
  const name = normalize(product.name);
  const tokens = name.split(" ");
  if (name === query) return { score: 100, match: "exact" };
  if (name.startsWith(query)) return { score: 92, match: "name_prefix" };
  if (tokens.some(token => token.startsWith(query))) return { score: 86, match: "token_prefix" };
  const hierarchy = normalize([product.name, product.specific_subcategory, product.subcategory, product.category]
    .filter(Boolean).join(" "));
  if (hierarchy.includes(query)) return { score: 72, match: "substring" };
  if (query.length < 4) return null;
  const max = query.length < 7 ? 1 : 2;
  const closest = Math.min(...tokens.map(token => distance(token, query, max)));
  return closest <= max ? { score: 60 - closest * 5, match: "fuzzy" } : null;
}

export function search(products: SearchProduct[], rawQuery: string, limit = 20): SearchResult[] {
  const query = normalize(rawQuery);
  if (query.length < 2) return [];
  return products.flatMap(product => {
    const result = rank(product, query);
    return result ? [{ ...product, ...result }] : [];
  }).sort((a, b) => b.score - a.score || a.name.localeCompare(b.name) || Number(a.id) - Number(b.id))
    .slice(0, Math.max(1, Math.min(50, limit)));
}

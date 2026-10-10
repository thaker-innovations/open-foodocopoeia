import searchIndex from "../worker/generated/search-index.json";
import { createSearch, type SearchProduct, type SearchResult } from "../worker/search";

const form = document.querySelector<HTMLFormElement>("#search")!;
const input = document.querySelector<HTMLInputElement>("#q")!;
const results = document.querySelector<HTMLElement>("#results")!;
const search = createSearch(searchIndex as SearchProduct[]);

function element(tag: string, text?: string, className?: string): HTMLElement {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function renderResult(result: SearchResult, query: string): HTMLElement {
  const link = element("a", undefined, "result") as HTMLAnchorElement;
  link.href = `/products/${encodeURIComponent(result.id)}/`;
  link.append(element("span", `#${result.id}`, "result-id"));
  const description = element("span");
  description.append(element("strong", result.name), element("small", result.category ?? ""));
  link.append(description, element("span", "View →", "match"));
  return link;
}

function run(rawQuery: string): void {
  const query = rawQuery.trim();
  results.replaceChildren();
  if (!query) return;
  const matches = search(query);
  if (!matches.length) {
    results.append(element("div", "No matching products.", "result"));
    return;
  }
  results.append(...matches.map(result => renderResult(result, query)));
}

function update(rawQuery: string): void {
  const query = rawQuery.trim();
  const url = query ? `?q=${encodeURIComponent(query)}` : location.pathname;
  history.replaceState(null, "", url);
  run(query);
}

input.addEventListener("input", () => update(input.value));
form.addEventListener("submit", event => {
  event.preventDefault();
  update(input.value);
});

const initialQuery = new URLSearchParams(location.search).get("q");
if (initialQuery) {
  input.value = initialQuery;
  run(initialQuery);
}

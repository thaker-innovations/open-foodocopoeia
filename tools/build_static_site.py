#!/usr/bin/env python3
"""Generate crawlable static product pages from the published dataset."""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import shutil
from xml.etree import ElementTree

BASE_URL = "https://open-foodocopoeia.thakerinnovations.com"
DISCLAIMER = (
    "Unofficial independent project; not affiliated with or endorsed by FSSAI. "
    "This is a ready reference, not a legal document. Original regulations and "
    "Gazette publications prevail."
)


def text(value: object | None) -> str:
    return escape("" if value is None else str(value))


def hierarchy(product: dict) -> list[str]:
    values = [
        product.get("category", {}).get("name"),
        product.get("subcategory", {}).get("name"),
        product.get("specific_subcategory", {}).get("name"),
    ]
    return [value for value in values if value and str(value).lower() != "n/a"]


def parameter_table(product: dict) -> str:
    rows = product["quality_parameters"]
    if not rows:
        return '<div class="empty">The source does not specify structured general quality parameters for this product.</div>'
    body = []
    for index, row in enumerate(rows, 1):
        variant = f'<span class="variant">{text(row.get("variant"))}</span>' if row.get("variant") else ""
        body.append(
            "<tr>"
            f'<td>{text(row.get("serial_number") or index)}</td>'
            f'<td>{text(row.get("parameter"))}{variant}</td>'
            f'<td>{text(row.get("fssr_limit"))}</td>'
            f'<td>{text(row.get("test_method") or "NS")}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="quality-table"><thead><tr><th>#</th><th>Parameter</th>'
        '<th>FSSR limit</th><th>Test method</th></tr></thead><tbody>'
        + "".join(body) + "</tbody></table></div>"
    )


def microbiological_table(product: dict) -> str:
    rows = product.get("microbiological_requirements", [])
    if not rows:
        return '<div class="empty">No structured microbiological requirements are specified for this product.</div>'
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f'<td>{text(row.get("parameter_type"))}</td>'
            f'<td>{text(row.get("parameter_code"))}</td>'
            f'<td>{text(row.get("parameter"))}</td>'
            f'<td>{text(row.get("sampling_plan_n"))}</td>'
            f'<td>{text(row.get("sampling_plan_c"))}</td>'
            f'<td>{text(row.get("limit_m"))}</td>'
            f'<td>{text(row.get("limit_M"))}</td>'
            f'<td>{text(row.get("unit"))}</td>'
            f'<td>{text(row.get("test_method") or "—")}</td>'
            "</tr>"
        )
    method_text = product.get("microbiological_test_method_text")
    note = ""
    if method_text:
        note = (
            '<details class="method-note"><summary>Microbiological test methods as published</summary>'
            f'<p>{text(method_text)}</p></details>'
        )
    return (
        '<div class="table-wrap"><table class="micro-table"><thead><tr><th>Type</th><th>Code</th>'
        '<th>Parameter</th><th>n</th><th>c</th><th>m</th><th>M</th><th>Unit</th>'
        '<th>Test method</th></tr></thead><tbody>' + "".join(body) + "</tbody></table></div>" + note
    )


def coded_requirement_section(product: dict, key: str, title: str) -> str:
    status = product.get(f"{key}_status", "not_specified")
    if status == "not_specified":
        return ""
    rows = product.get(f"{key}_requirements", [])
    method = product.get(f"{key}_test_method_text")
    method_is_specified = bool(method and str(method).strip().upper() not in {"NS", "N/A", "NA", "-", "."})
    body = "".join(
        "<tr>"
        f'<td>{text(row.get("raw_code"))}</td>'
        f'<td>{text(row.get("analyte_or_requirement") or "—")}</td>'
        f'<td>{text(row.get("limit_text") or "—")}</td>'
        f'<td>{text(row.get("test_method") or ("Section-level methods below" if method_is_specified else "Not specified by source"))}</td>'
        "</tr>" for row in rows
    )
    table = (
        '<div class="table-wrap"><table class="coded-table"><thead><tr><th>Source code</th>'
        '<th>Analyte or requirement</th><th>Limit as published</th><th>Test method</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>' if rows else ""
    )
    raw = product.get(f"{key}_text")
    source = f'<details class="method-note"><summary>Source section text</summary><p>{text(raw)}</p></details>' if raw else ""
    published_method = text(method) if method_is_specified else "Not specified by the source."
    methods = f'<div class="published-methods"><strong>Test methods as published</strong><p>{published_method}</p></div>'
    count = f"{len(rows)} coded requirements" if rows else "Narrative requirement"
    return f'<section><div class="section-head"><h2>{text(title)}</h2><p>{count}</p></div>{methods}{table}{source}</section>'


def fatty_acid_section(product: dict) -> str:
    rows = product.get("fatty_acid_composition", [])
    if not rows:
        return ""
    body = "".join(
        f'<tr><td>{text(row.get("fatty_acid"))}</td><td>{text(row.get("composition_limit"))}</td><td>{text(row.get("test_method") or "—")}</td></tr>'
        for row in rows
    )
    return (
        f'<section><div class="section-head"><h2>Fatty-acid composition</h2><p>{len(rows)} rows</p></div>'
        '<div class="table-wrap"><table class="coded-table"><thead><tr><th>Fatty acid</th><th>Composition</th><th>Test method</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div></section>'
    )


def regulatory_sections(product: dict) -> str:
    sections = [
        coded_requirement_section(product, "pesticide_residue", "Pesticide and insecticide residues"),
        coded_requirement_section(product, "heavy_metal", "Heavy metals"),
        coded_requirement_section(product, "antibiotic_veterinary_drug", "Antibiotic and veterinary-drug residues"),
        coded_requirement_section(product, "contaminant", "Toxins and other contaminants"),
        fatty_acid_section(product),
    ]
    if product.get("food_additive_status") == "available":
        sections.append(
            '<section><div class="section-head"><h2>Food additives</h2><p>Source allowance text</p></div>'
            f'<div class="raw-section">{text(product.get("food_additive_text"))}</div></section>'
        )
    return "".join(sections)


def product_page(product: dict) -> str:
    product_id = text(product["id"])
    name = text(product["name"])
    crumbs = "".join(f"<span>{text(value)}</span>" for value in hierarchy(product))
    canonical = f"{BASE_URL}/products/{product_id}/"
    description = text(f"Published quality, microbiological, residue and contaminant requirements for {product['name']} from the unofficial Open Food-'O'-Copoeia dataset.")
    provenance = product["provenance"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{name} · Open Food-'O'-Copoeia</title>
  <meta name="description" content="{description}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{name} · Open Food-'O'-Copoeia">
  <meta property="og:description" content="{description}">
  <meta property="og:url" content="{canonical}">
  <link rel="stylesheet" href="/product.css">
</head>
<body>
  <div class="topline"><div><span>An open-data project maintained by <a href="https://thakerinnovations.com/">Thaker Innovations Pvt. Ltd.</a></span><a class="mcp" href="/mcp/setup/">Use with MCP</a></div></div>
  <div class="bar"><header><a class="brand" href="/">Open Food-'O'-Copoeia</a><a class="back" href="/">← Back to search</a></header></div>
  <main><article>
    <section class="hero"><div class="kicker">Product #{product_id}</div><div class="crumbs">{crumbs}</div><h1>{name}</h1></section>
    <section><div class="section-head"><h2>General quality parameters</h2><p>Limits and methods as represented in the source reference.</p></div>{parameter_table(product)}</section>
    <section><div class="section-head"><h2>Microbiological requirements</h2><p>Sampling plans and hygiene or safety limits.</p></div>{microbiological_table(product)}</section>
    {regulatory_sections(product)}
    <section class="provenance"><div class="prov"><label>Retrieved</label><div>{text(provenance.get("retrieved_at") or "Not recorded")}</div></div><div class="prov"><label>Source fingerprint</label><div>{text(provenance.get("source_sha256") or "Not recorded")}</div></div></section>
    <div class="actions"><a class="button" href="/api/v1/products/{product_id}">View JSON</a></div>
  </article></main>
  <footer class="notice"><p>{text(DISCLAIMER)}</p></footer>
</body>
</html>
"""


def directory_page(products: list[dict]) -> str:
    links = "".join(
        f'<li><a href="/products/{text(product["id"])}/">{text(product["name"])}</a>'
        f'<span>{text(product.get("category", {}).get("name"))}</span></li>'
        for product in products
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Products · Open Food-'O'-Copoeia</title><meta name="description" content="Browse all Food-'O'-Copoeia product entries.">
<link rel="canonical" href="{BASE_URL}/products/"><link rel="stylesheet" href="/product.css"></head>
<body><div class="topline"><div><span>An open-data project maintained by <a href="https://thakerinnovations.com/">Thaker Innovations Pvt. Ltd.</a></span><a class="mcp" href="/mcp/setup/">Use with MCP</a></div></div><div class="bar"><header><a class="brand" href="/">Open Food-'O'-Copoeia</a><a class="back" href="/">← Search</a></header></div>
<main class="directory"><h1>Products</h1><ul>{links}</ul></main><footer class="notice"><p>{text(DISCLAIMER)}</p></footer></body></html>
"""


def sitemap(products: list[dict], snapshot: str) -> str:
    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ElementTree.register_namespace("", namespace)
    root = ElementTree.Element(f"{{{namespace}}}urlset")
    paths = ["/", "/products/", "/mcp/setup/"] + [f'/products/{product["id"]}/' for product in products]
    for path in paths:
        url = ElementTree.SubElement(root, f"{{{namespace}}}url")
        ElementTree.SubElement(url, f"{{{namespace}}}loc").text = BASE_URL + path
        ElementTree.SubElement(url, f"{{{namespace}}}lastmod").text = snapshot[:10]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(root, encoding="unicode") + "\n"


def build(public: Path, snapshot: str) -> int:
    data_path = public / "data" / f"v{snapshot}" / "products.json"
    products = json.loads(data_path.read_text(encoding="utf-8"))
    output = public / "products"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / "index.html").write_text(directory_page(products), encoding="utf-8")
    for product in products:
        directory = output / str(product["id"])
        directory.mkdir()
        (directory / "index.html").write_text(product_page(product), encoding="utf-8")
    (public / "sitemap.xml").write_text(sitemap(products, snapshot), encoding="utf-8")
    (public / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8"
    )
    return len(products)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, default=Path("public"))
    parser.add_argument("--snapshot", default="2026-10-10.2")
    args = parser.parse_args()
    print(f"Generated {build(args.public, args.snapshot)} product pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

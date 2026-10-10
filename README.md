# Open Food-'O'-Copoeia

An unofficial, open-source API and reproducible dataset for the public FSSAI
Food-'O'-Copoeia reference.

> **Not affiliated with or endorsed by FSSAI.** Food-'O'-Copoeia is a ready
> reference, not a legal document. Original FSS regulations, Gazette
> publications, and FSSAI advisories, orders, directions and manuals prevail.

## API

```bash
curl 'https://open-foodocopoeia.thakerinnovations.com/api/v1/search?q=ric'
curl 'https://open-foodocopoeia.thakerinnovations.com/api/v1/products/48'
curl 'https://open-foodocopoeia.thakerinnovations.com/api/v1/meta'
```

Search uses MiniSearch with weighted product and hierarchy fields, unordered
multi-word matching, prefixes, and bounded typo tolerance. `q=ric` finds `Rice`,
while `q=others%20oil` matches words anywhere in the product hierarchy. The
website bundles the same index for instant search on every keystroke; the Worker
provides the same behavior through the public API.

## MCP

Connect an MCP client to the public, read-only Streamable HTTP endpoint:

```text
https://open-foodocopoeia.thakerinnovations.com/mcp
```

Setup instructions and available tools are documented at
[open-foodocopoeia.thakerinnovations.com/mcp/setup/](https://open-foodocopoeia.thakerinnovations.com/mcp/setup/).

## Current snapshot

- 504 products
- 457 products with quality parameters
- 4,923 normalized general quality-parameter rows
- 258 products with microbiological requirements
- 1,809 normalized microbiological-requirement rows
- 36 products manually reviewed after deterministic parsing
- 47 products where the source gives no structured quality parameters

The API uses a Cloudflare Worker and static assets—no database or paid hosting.
Every product also has a crawlable static page under `/products/{id}/`; the
custom subdomain publishes `sitemap.xml` and `robots.txt`. See [API
documentation](docs/api.md), [methodology](docs/methodology.md), and the [data
notice](DATA-NOTICE.md).

## Local development

```bash
npm install
python3 tools/build_public_dataset.py --input work/products.jsonl
npm run check
npm run dev
```

The normalized snapshot is committed under `public/data/`. Source captures are
not committed; a future release workflow will attach compressed capture bundles
and checksums to GitHub Releases.

## Repository roles

- `scraper/` — respectful ASP.NET capture and deterministic normalization
- `overrides/` — reviewed resolutions for source tables too irregular to infer
- `tools/` — reproducible dataset and static-site builders
- `worker/` — API and ranked search
- `web/` — browser MiniSearch entrypoint
- `public/` — immutable snapshots, static downloads, and generated site assets

Open Food-'O'-Copoeia is an open-data project maintained by [Thaker Innovations
Pvt. Ltd.](https://thakerinnovations.com/). Software is MIT licensed. See
[DATA-NOTICE.md](DATA-NOTICE.md) for the separate data/source notice.

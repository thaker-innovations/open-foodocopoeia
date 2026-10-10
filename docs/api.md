# API

Base URL: `https://open-foodocopoeia.tapan-d-thaker.workers.dev`

## `GET /api/v1/search`

Parameters:

- `q`: required, 2–100 characters
- `limit`: optional, 1–50; default 20

Ranking order: exact name, name prefix, word prefix, hierarchy substring, then
bounded edit distance. Ties are deterministic by product name and identity.

```http
GET /api/v1/search?q=ric&limit=10
```

## `GET /api/v1/products/{identity}`

Returns the full product hierarchy, quality parameters, test methods, parser
confidence and source provenance. Product identities are stable source IDs.

## `GET /api/v1/meta`

Returns schema and snapshot versions, counts, source disclaimer, and artifact
checksums.

## Downloads

- `/downloads/latest/products.json`
- `/downloads/latest/products.csv`
- `/downloads/latest/quality-parameters.json`
- `/downloads/latest/quality-parameters.csv`

All API responses are public, read-only, and CORS-enabled. No API key is needed.

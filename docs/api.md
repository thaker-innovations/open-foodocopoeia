# API

Base URL: `https://open-foodocopoeia.thakerinnovations.com`

## `GET /api/v1/search`

Parameters:

- `q`: required, 2–100 characters
- `limit`: optional, 1–50; default 20

MiniSearch evaluates each query word independently across weighted product name,
specific subcategory, subcategory, and category fields. All query words must
match, in any order. Exact and name-prefix results rank above token-prefix,
substring, and bounded fuzzy matches.

```http
GET /api/v1/search?q=ric&limit=10
GET /api/v1/search?q=others%20oil&limit=10
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

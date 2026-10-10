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

Returns the full product hierarchy, general quality parameters,
microbiological requirements, pesticide and veterinary-drug residues, heavy
metals, contaminants, food-additive text, fatty-acid composition, test methods,
parser confidence and source provenance. Product identities are stable source
IDs. Limits remain strings because the source may publish inequalities, ranges,
qualifiers, `Absent`, or `NS`.

## `GET /api/v1/meta`

Returns schema and snapshot versions, counts, source disclaimer, and artifact
checksums.

## Downloads

- `/downloads/latest/products.json`
- `/downloads/latest/products.csv`
- `/downloads/latest/quality-parameters.json`
- `/downloads/latest/quality-parameters.csv`
- `/downloads/latest/microbiological-requirements.json`
- `/downloads/latest/microbiological-requirements.csv`
- `/downloads/latest/pesticide-residue-requirements.json`
- `/downloads/latest/pesticide-residue-requirements.csv`
- `/downloads/latest/heavy-metal-requirements.json`
- `/downloads/latest/heavy-metal-requirements.csv`
- `/downloads/latest/antibiotic-veterinary-drug-requirements.json`
- `/downloads/latest/antibiotic-veterinary-drug-requirements.csv`
- `/downloads/latest/contaminant-requirements.json`
- `/downloads/latest/contaminant-requirements.csv`
- `/downloads/latest/fatty-acid-composition.json`
- `/downloads/latest/fatty-acid-composition.csv`
- `/downloads/latest/food-additive-allowances.json`
- `/downloads/latest/food-additive-allowances.csv`

All API responses are public, read-only, and CORS-enabled. No API key is needed.

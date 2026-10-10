# Methodology

The source website uses ASP.NET Web Forms. The capture client maintains the
session cookie and posts `__VIEWSTATE` for alphabet filters and product View
actions. It follows the public interaction flow sequentially and rate-limits
requests.

Normalization has three levels:

1. Standard product quality grids are parsed deterministically.
2. Clear alternate HTML tables are normalized only when column meaning is
   unambiguous; product variants become separate rows.
3. Complex matrices and narrative requirements are dumped for human review.
   Reviewed replacements live in `overrides/manual_quality_overrides.json`.

Ambiguous labels are qualified using their hierarchy. A source value of `N/A`
at the specific-subcategory level falls back to the subcategory or category.
`Others` becomes a contextual name such as `Others — Lager (BEER)`.

Every published product preserves retrieval time, source URL, and source-body
SHA-256. Empty source requirements are represented as `not_specified`, never as
zero. Builds sort records and keys to keep snapshots deterministic.

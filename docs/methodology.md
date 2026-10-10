# Methodology

The source website uses ASP.NET Web Forms. The capture client maintains the
session cookie and posts `__VIEWSTATE` for alphabet filters and product View
actions. It follows the public interaction flow sequentially and rate-limits
requests.

General quality normalization has three levels:

1. Standard product quality grids are parsed deterministically.
2. Clear alternate HTML tables are normalized only when column meaning is
   unambiguous; product variants become separate rows.
3. Complex matrices and narrative requirements are dumped for human review.
   Reviewed replacements live in `overrides/manual_quality_overrides.json`.

The dedicated `GVMicroBioParam` grid is normalized separately as
`microbiological_requirements`. Each row retains its hygiene/safety type,
parameter code, organism or parameter, sampling-plan `n` and `c`, lower `m` and
upper `M` limits, and unit. Microbiological rows are never mixed into general
quality rows.

The source publishes microbiological test methods as a separate text block.
Methods are attached to rows only when the text contains an unambiguous exact
parameter-code mapping. The complete source text is retained, and unresolved
mappings are marked rather than inferred by row order or parameter similarity.

Ambiguous labels are qualified using their hierarchy. A source value of `N/A`
at the specific-subcategory level falls back to the subcategory or category.
`Others` becomes a contextual name such as `Others — Lager (BEER)`.

Every published product preserves retrieval time, source URL, and source-body
SHA-256. General quality and microbiological availability have independent
statuses; an empty general quality section does not imply that microbiological
requirements are absent. Builds sort records and keys to keep snapshots
deterministic.

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

Pesticide/insecticide residues, heavy metals, antibiotic and veterinary-drug
residues, and toxins or other contaminants are published as compact coded text
sections. Recognizable source tokens are split conservatively into code and
parenthesized limit text. Analyte names come from separately captured FSSAI code
lists whose URLs and SHA-256 hashes are committed in
`scraper/parameter_codes.json`. Source codes, expressions, complete section
text, and section-level test-method text are retained. Units, commodity context,
source typos, and per-row test methods are not inferred.

The dedicated fatty-acid grid is normalized independently. Food-additive
allowances are retained as product-level source text because their dense,
product-specific matrices cannot be split reliably without interpretation.

Ambiguous labels are qualified using their hierarchy. A source value of `N/A`
at the specific-subcategory level falls back to the subcategory or category.
`Others` becomes a contextual name such as `Others — Lager (BEER)`.

Every published product preserves retrieval time, source URL, and source-body
SHA-256. General quality and microbiological availability have independent
statuses; an empty general quality section does not imply that microbiological
requirements are absent. Builds sort records and keys to keep snapshots
deterministic.

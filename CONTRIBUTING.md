# Contributing

Bug reports, parser fixtures, documentation corrections and reviewed data
corrections are welcome.

For a data correction, include the product identity, source URL, captured-source
hash, exact affected row, and the reason for the change. Do not silently rewrite
an existing snapshot; corrections produce a new versioned snapshot.

Run before opening a pull request:

```bash
npm install
npm run check
```

Do not add FSSAI logos, secrets, browser profiles, or unreviewed generated
captures to the repository.

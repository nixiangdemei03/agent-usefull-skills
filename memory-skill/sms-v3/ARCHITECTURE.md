# SMS v3 — Architecture

> Three-tier memory: raw logs → daily files → consolidated. The foundation of the current system.

## Three Tiers
- 🥉 raw/: Minimal format logs (~50B/entry, never deleted)
- 🥈 auto/*.json: Daily full-detail entries with tags
- 🥇 curated/consolidated.json: Fingerprint-merged, score-sorted, title_only compression

## Scoring
`score = hit_count × recency_factor`

## Compression
Cloud-free: pure file stat + string operations (~0.2s for 500 entries).

# SMS v3 — Architecture

> Version: 3.0 | Three-tier memory: raw logs → daily files → consolidated

## Overview

SMS v3 introduces the three-tier storage that is the foundation of v4. Added raw log permanent storage, daily dedup files, and cross-day compression into consolidated.json.

## Three-Tier Storage

```
🥉 auto/raw/YYYY-MM-DD.raw.json   ← Minimal format (~50B/entry, never deleted)
🥈 auto/YYYY-MM-DD.json            ← Full detail entries with tags
🥇 curated/consolidated.json       ← Fingerprint-merged, score-sorted, title_only compression
```

## New in v3

| Feature | Description |
|---------|-------------|
| Raw logs | Permanent audit trail in minimal format |
| Daily files | Full detail per day with tags |
| Consolidated | Cross-day dedup + merge |
| Dirty check | Skip compress if no changes (0.001s) |
| Title only | Cold entries reduced to ~100 bytes |
| Git sync | JSON diff/merge for collaboration |

## Scoring

`score = hit_count × recency_factor`

## Limitations vs v4

- No FTS5 full-text search
- No CJK/ASCII boundary tokenization
- No auto-compress cron
- No CLAUDE.md auto-recording rules

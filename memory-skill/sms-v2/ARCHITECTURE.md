# SMS v2 — Architecture

> Version: 2.0 | Added fingerprint dedup + hit_count scoring

## Overview

SMS v2 introduces automatic dedup via fingerprint matching. Every entry gets a unique fingerprint derived from tags + summary prefix. When writing, existing entries with the same fingerprint are merged (hit_count incremented) instead of duplicated.

## Key Features

| Feature | Description |
|---------|-------------|
| Fingerprint dedup | `fingerprint = sorted(tags) + '|' + summary[:50].lower()` |
| hit_count tracking | Each merge increments hit_count |
| score calculation | `score = hit_count × recency_factor` |
| Auto tiering | hot (score ≥8, max 20), warm (≥3, max 100), cold (<3) |

## Limitations vs v4

- No FTS5 full-text search
- No CJK/ASCII boundary tokenization
- No raw log permanent storage
- No auto-compress cron
- No CLAUDE.md auto-recording rules

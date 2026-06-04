# SMS v2 — Memory Skill

> Fingerprint dedup + hit_count scoring. Records on demand.

## Core Flow

1. User mentions something notable → use `write_or_merge`
2. System checks fingerprint → if exists, merge (hit_count++) else create
3. Score recalculated during compress
4. High-score entries auto-promoted to hot tier

## Limitations

- No automatic recording — agent must decide to call tools
- No CLAUDE.md rules — v4 has them

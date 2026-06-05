# Smart Memory System v4 — Agent Behavior Guide

> MEMORY_SKILL.md
> This file defines how I (the agent) should automatically manage memory.
> Read this once at session start and follow its rules.

---

## Core Principle

**Write before you ask: "Have I seen this before?"**
Every time you learn something, check if it already exists first.
If it does → merge (increment hit_count). If not → create new.

---

## Three-Tier Architecture

```
🥇 curated/consolidated.json   ← Highest priority: all entries, score-sorted
🥈 auto/YYYY-MM-DD.json         ← Daily full-detail entries
🥉 auto/raw/*.raw.json           ← Minimal logs (50B/entry, never deleted)
⚡ fts/memory.db                 ← SQLite FTS5 full-text search index (auto-rebuilt)
```

Search order:
1. `search_fts()` → FTS5 fuzzy search (fastest, most flexible)
2. `search_memories()` → tag/type/keyword search
3. If title_only hit → backtrack via fingerprint to raw log

---

## What to Remember (Auto-Capture Triggers)

| Trigger | Type | Example |
|---------|------|---------|
| New command/API/config | `knowledge` | "curl -X POST with headers" |
| User preference/habit | `preference` | "Prefers JSON over YAML" |
| Decision with reason | `decision` | "Chose Django for team familiarity" |
| Fixed error/bug | `failure` | "403 → token expired, refresh to fix" |
| Task completed | `event` | "Deployed to production" |
| Cross-session pattern | `insight` | "User always starts projects with JSON schema" |
| "remember this" | varies | User explicitly asked |

## What NOT to Remember

Greetings, acknowledgments ("ok", "thanks"), transient status ("let me check"), unresolved discussions, raw error text without a fix.

## Fingerprint Dedup

`fingerprint = sorted(tags).join(',') + '|' + summary[0:50].lower()`

Same fingerprint = same knowledge. Use `write_or_merge` — it handles dedup automatically.

## Scoring

```
score = hit_count × recency_factor
  < 1 day  → 3.0
  < 7 days → 1.5
  < 30 days → 1.0
  else     → 0.5
```

Tiers: hot (score ≥ 8, auto-loaded, max 20), warm (≥ 3, searchable), cold (< 3, title_only)

## Important

- **Never wait for the user to say "remember this".** Record automatically.
- **Tags determine dedup quality.** Use specific, searchable tags.
- **Search before answering history questions.** Try 2-3 keywords.
- **Hit memory entries you reference.** Call `hit_memory(id)` to boost scores.
- **Run compress.py periodically** to rebuild the FTS5 index and consolidate.

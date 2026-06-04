# SMS v4 — Architecture Document

> Smart Memory System v4
> A three-tier local memory system for AI agents with FTS5 full-text search.

---

## Overview

SMS is a persistent memory system for AI agents (Claude Code, OpenClaw, Gemini CLI, etc.).
It stores structured memories in JSON files and provides fast full-text search via SQLite FTS5.

**Key design principles:**
- Pure local — no cloud, no API, no vector database
- Human-readable — all data is JSON, viewable in notepad
- Git-friendly — JSON diff/merge for team collaboration
- Zero-cost compression — no LLM calls needed for maintenance

---

## Three-Tier Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    🥇 CONSOLIDATED                            │
│                   curated/consolidated.json                   │
│          All entries: fingerprint-merged, score-sorted        │
│          Hot (20) → high score, full detail                   │
│          Cold (rest) → title_only + source pointer            │
│          First lookup target                                   │
├──────────────────────────────────────────────────────────────┤
│                    🥈 DAILY FILES                             │
│                   auto/YYYY-MM-DD.json                        │
│          Full detail entries per day                          │
│          Tags, context, author, contributors                  │
│          Second lookup target                                  │
├──────────────────────────────────────────────────────────────┤
│                    🥉 RAW LOGS                                │
│                  auto/raw/YYYY-MM-DD.raw.json                 │
│          Minimal format (~50 bytes/entry)                     │
│          Never deleted — permanent audit trail                │
├──────────────────────────────────────────────────────────────┤
│                    ⚡ FTS5 SEARCH INDEX                       │
│                    fts/memory.db                              │
│          SQLite FTS5 full-text search                         │
│          Auto-rebuilt during compress                         │
│          CJK/ASCII boundary tokenized for mixed-language text │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
Conversation produces knowledge point
         │
         ├─→ auto/raw/*.raw.json   ← minimal log (50B, never deleted)
         │
         ├─→ auto/*.json            ← full detail with tags
         │
         └─→ compress.py triggers
                  │
                  ├─ 1. dirty check (stat mtime, 0.001s skip)
                  ├─ 2. read raw + auto + previous consolidated
                  ├─ 3. fingerprint group → dedup merge
                  ├─ 4. score = hit_count × recency
                  ├─ 5. tier allocation (hot/warm/cold)
                  ├─ 6. title_only downgrade for cold entries
                  ├─ 7. write consolidated.json
                  └─ 8. rebuild FTS5 index
```

---

## Scoring

```
score = hit_count × recency_factor

recency_factor:
  < 1 day  → 3.0    (just mentioned)
  < 7 days → 1.5    (this week)
  < 30 days → 1.0   (this month)
  else     → 0.5    (long ago)
```

### Tiers

| Tier | Score | Max | Session behavior |
|------|-------|-----|-----------------|
| 🔥 hot | ≥ 8 | 20 | Auto-injected into system prompt |
| ☀️ warm | ≥ 3 | 100 | Searchable, not auto-loaded |
| ❄️ cold | < 3 | ∞ | Title only, full detail via raw backtrack |
| 🗑️ archive | — | — | Knowledge relocated to external docs |

---

## Title Only Compression

Cold entries automatically get compressed to just their title (~100 bytes vs ~500 bytes for full detail):

```json
// Cold entry (title_only)
{
  "summary": "Darling习惯怎么称呼我",
  "title_only": true,
  "source_raw": "auto/raw/2026-06-04.raw.json",
  "score": 1.5
}
```

The title itself answers most questions. If full detail is needed, backtrack by fingerprint to the raw log.

---

## Fingerprint Dedup

Each entry has a `fingerprint` = `sorted(tags).join(',') + '|' + summary[0:50].lower()`

Same fingerprint → same knowledge → automatic merge on compress:
- hit_count adds up
- contributors merge
- detail combines with author prefix
- score recalculates

---

## FTS5 Search

SQLite FTS5 with CJK/ASCII boundary tokenization:

```
Before: "Q2用pipe chain实现'AA before BB'"
After:  "Q2 用 pipe chain 实现'AA before BB'"
```

Allows searching "pipe", "chain", "grep" in mixed Chinese-English text.

Search types:
| Method | Tool | Speed | Fuzzy |
|--------|------|-------|-------|
| fingerprint | write_or_merge | instant | exact only |
| exact | search_memories | ~50ms | no |
| **full-text** | **search_fts** | **~5ms** | **yes (FTS5 BM25)** |

---

## MCP Server Tools

| Tool | Description |
|------|-------------|
| `search_fts` | FTS5 full-text search, fuzzy matching, BM25 ranking |
| `search_memories` | Legacy tag/type/keyword search |
| `write_or_merge` | Write new entry with fingerprint dedup |
| `hit_memory` | Mark entry as referenced (increase score) |
| `get_context` | Get current hot tier context |
| `get_stats` | System statistics and tier distribution |

---

## File Structure

```
sms-memory/                      ← configurable during install
├── schema.json                  ← data format definition
├── fts/
│   └── memory.db                ← SQLite FTS5 search index
├── auto/
│   ├── raw/                     ← minimal raw logs (never delete)
│   └── YYYY-MM-DD.json          ← daily full-detail entries
├── curated/
│   └── consolidated.json        ← priority-1 retrieval target
├── cache/
│   └── memory_cache.json        ← hot tier context cache
└── scripts/
    ├── compress.py              ← main compress engine
    ├── rebuild_fts.py           ← FTS5 index builder
    ├── consolidate.sh           ← shell consolidation wrapper
    ├── cache_refresh.sh         ← cache updater
    └── _summary.py              ← tier summary helper
```

---

## Comparison: SMS v4 vs claude-mem

| Dimension | claude-mem | SMS v4 |
|-----------|-----------|--------|
| Storage | SQLite + Chroma vector DB | **JSON + SQLite FTS5** |
| Compression | LLM summarization (seconds) | **File stat + merge (milliseconds)** |
| Search | Vector semantic (fuzzy) | **FTS5 full-text (precision + recall)** |
| Token cost | ~26,800t/day | **~1,660t/day** |
| Offline | ❌ Requires Chroma service | ✅ **Fully offline** |
| Human-readable | ❌ Binary vectors | ✅ **cat any JSON file** |
| Git collaboration | ❌ Not supported | ✅ **JSON diff/merge** |
| Compression time (500 entries) | ~30-60s | **~0.2s** |
| Dependencies | Chroma + SQLite + Node | **Node.js + Python3 only** |
| Data control | Anthropic server | **Your local filesystem** |

---

## Automation

SMS v4 runs fully automatically with zero manual intervention:

### Minute-by-minute (60s cron)
```
Every 60 seconds → compress.py --auto
  ├─ Was last compress < 60s ago?  → skip (anti-racing)
  ├─ Any new data since last run?  → skip (dirty check, 0.001s)
  └─ New data + idle > 60s         → full compress (0.2s)
       ├─ fingerprint dedup + merge
       ├─ score recalculation
       ├─ title_only downgrade
       ├─ write consolidated.json
       ├─ rebuild FTS5 index
       └─ update .last_compress lock
```

### Daily midnight at local system time — works in any timezone
```
Full compress regardless of changes.
Ensures FTS5 index is always rebuilt at least once per day.
```

### CLAUDE.md (auto-recording)
Placed at `~/CLAUDE.md` during install. Claude Code follows these rules:
- Automatically calls `write_or_merge` on new knowledge/preference/decision/failure
- Automatically calls `search_fts` before answering history questions
- Filters out greetings, acknowledgments, and noise
- No user command required — works silently in background

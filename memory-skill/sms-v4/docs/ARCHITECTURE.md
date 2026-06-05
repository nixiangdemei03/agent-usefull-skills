# SMS v4 — Architecture Document

> Smart Memory System v4.05
> A three-tier local memory system for AI agents with automatic compression and supersedes-aware search.

---

## Overview

SMS is a persistent memory system for AI agents (Claude Code, OpenClaw, Gemini CLI, etc.).
It stores structured memories in JSON files, provides fast full-text search via SQLite FTS5,
and automatically compresses/degrades memories based on importance, recency, and frequency.

**Key design principles:**
- Pure local — no cloud, no API, no vector database
- Human-readable — all data is JSON, viewable in notepad
- Git-friendly — JSON diff/merge for team collaboration
- Zero-cost compression — no LLM calls needed for maintenance
- Automation — idle detection + scheduled compression + exchange demotion

**Current version: v4.05**

---

## Three-Tier Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    🥇 CONSOLIDATED                            │
│                   curated/consolidated.json                   │
│          All entries: fingerprint-merged, score-sorted        │
│                                                                  │
│          🔥 Hot  (20 max)  → high score, full detail          │
│              Auto-injected into every session context          │
│                                                                  │
│          ☀️ Warm (100 max) → medium score, full detail         │
│              Searchable, not auto-loaded                       │
│                                                                  │
│          ❄️ Cold (∞)       → title_only + SQLite pointer       │
│              Detail stored in fts/memory.db, O(1) retrieval    │
│              Superseded entries forced to cold on compress     │
│                                                                  │
│          First lookup target                                    │
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
│          Supersedes-aware: defaults to filtering old entries  │
│          CJK/ASCII boundary tokenized for mixed-language text │
└──────────────────────────────────────────────────────────────┘
```

---

## Scoring Formula

```
Score = I × e^(-λt) × log(1 + f)

I = importance (1-10, required on write)
λ = ln(2) / 21  (half-life = 21 days, single continuous λ)
t = days since last hit
f = hit_count
```

Activity labels (human-readable, not separate λ values):
| Period | Label |
|--------|-------|
| < 14 days | 🔥 High activity |
| 14-28 days | ☀️ Medium activity |
| 28-42 days | 🌥️ Low activity |
| > 42 days | 🌙 Weak activity |

### Superseded penalty

Entries marked `superseded: true` are **forced to cold** on every compress,
regardless of score. The vacated hot/warm slots are immediately refilled
by the next highest-scored active entries.

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
                  ├─ 4. score = I × e^(-λt) × log(f+1)
                  ├─ 5. exchange demotion (hot↔warm↔cold, count-matched)
                  ├─ 6. forced: superseded → cold, refill hot/warm
                  ├─ 7. title_only downgrade for cold entries
                  ├─ 8. cold detail → SQLite memories table
                  ├─ 9. write consolidated.json
                  └─ 10. rebuild FTS5 index
```

### Compress Triggers

| Trigger | Condition | Behavior |
|---------|-----------|----------|
| **Idle** | Windows user idle > 5 min (GetLastInputInfo) + 6 consecutive samples | New data → compress. No data → skip |
| **Scheduled** | Daily at 00:00 system time | Full compress + exchange demotion + FTS5 rebuild |

---

## Exchange Demotion

```
Before compress:
  Hot (20)         Warm (N)         Cold (∞)

After score recalc:
  Hot-bottom → Warm-front  (lowest-scored hot entries)
  Warm-bottom → Cold       (same count as hot→warm)
  
  Warm saturation < 90%?  → Cold eviction suppressed
  Warm exceeds 100?       → Overflow accepted, gradually digested
```

Key rule: **number of entries demoted = number of entries promoted**,
ensuring no slot waste and no overflow spikes.

---

## Supersedes Mechanism

When new knowledge replaces old (e.g., rename from "NS5" to "Elio"):

```
write_or_merge(
  summary="My name is Elio",
  importance=10,
  supersedes=["mem-old-name-id"]
)
```

### Effects

| Search mode | Default behavior | Historical query |
|-------------|-----------------|------------------|
| `search_memories` | Returns only active (non-superseded) | Detects "before"/"previously" keywords → shows all |
| `search_fts` | Filters superseded entries | Same — triggered by historical keywords |
| `get_context` | Only active entries | — |
| `compress.py` | Forces superseded → cold + title_only | — |
| `update_entry` | Can restore: `tier="hot"` reverses it | — |

Historical keywords: "以前", "之前", "原来", "以前叫什么", "几月几号", "previous", "old name", etc.
Results ordered by `supersedes_index DESC` (newest first).

---

## Fingerprint Dedup

**v4.03+**: `fingerprint = summary.trim().slice(0,50).toLowerCase()`

No longer includes tags. Backward compatible: search by both old format (`tags|summary`)
and new format (`summary-only`) during lookup.

Same fingerprint → same knowledge → automatic merge on compress:
- hit_count adds up
- contributors merge
- detail combines with source prefix
- score recalculates

---

## FTS5 Search

SQLite FTS5 with CJK/ASCII boundary tokenization:

```
Before: "Q2用pipe chain实现'AA before BB'"
After:  "Q2 用 pipe chain 实现'AA before BB'"
```

**Supersedes filtering:**
```sql
WHERE memories_fts MATCH ?
  AND (m.superseded IS NULL OR m.superseded = 0)
```

Search types:
| Method | Tool | Speed | Fuzzy | Supersedes-aware |
|--------|------|-------|-------|-----------------|
| fingerprint | write_or_merge | instant | exact only | ✅ |
| exact | search_memories | ~50ms | no | ✅ |
| **full-text** | **search_fts** | **~5ms** | **yes (FTS5 BM25)** | ✅ |
| LIKE fallback | search_fts | ~50ms | yes | ✅ |

---

## MCP Server Tools (v4.05)

| Tool | Description |
|------|-------------|
| `search_fts` | FTS5 full-text search, fuzzy matching, BM25 ranking. Supersedes-aware |
| `search_memories` | Legacy tag/type/keyword search. Supports historical query mode |
| `write_or_merge` | Write new entry with fingerprint dedup. **importance required.** Optional `supersedes` param |
| `hit_memory` | Mark entry as referenced. Three-way writeback: auto→consolidated→SQLite |
| `get_context` | Get current hot tier context (real-time, no stale cache) |
| `get_stats` | System statistics with mutually exclusive tier counting |
| `recalc_score` | Recalculate score for one or all entries using new formula |
| `update_entry` | Update tier, importance, or supersedes state directly |

---

## Idle Detection

```
Windows side (idle-detect.ps1):
  GetLastInputInfo → every 10s → writes to .claude/idle_state.txt

WSL/Compress side (compress.py --auto):
  Read idle_state.txt → 6 consecutive idle samples (>5 min) → trigger
  Fallback: direct PowerShell if file unavailable
  No idle detection → skip compress
```

---

## File Structure (v4.05)

```
sms-v4/
├── README.md              ← Overview
├── docs/                  ← Documentation
│   ├── ARCHITECTURE.md    Architecture (EN)
│   ├── ARCHITECTURE.zh.md Architecture (ZH)
│   ├── INSTALL.md         Installation guide (EN/ZH)
│   ├── MEMORY_SKILL.md    Agent behavior guide
│   ├── 版本优化详情.md     Version changelog
│   └── SMS_vs_Claude_     Comparison with claude-mem
├── install/               ← Installation & code
│   ├── install.sh         One-click installer
│   ├── server.js          MCP server
│   ├── schema.json        Data format (v4.05)
│   ├── CLAUDE.md.template Auto-recording rules
│   ├── scripts/           compress.py, rebuild_fts.py, etc.
│   └── package.json       Dependencies
```

---

## Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| **v4.05** | 2026-06-05 | Superseded forced→cold + Hot refill |
| v4.04 | 2026-06-05 | FTS5 supersedes filter + SQLite columns |
| v4.03 | 2026-06-05 | Supersedes mechanism + historical search + 7 bugs fixed |
| v4.02 | 2026-06-05 | MCP tools (recalc_score/update_entry) + idle-detect.ps1 |
| v4.01 | 2026-06-05 | Compress engine v3: new scoring, exchange demotion, SQLite cold |
| v4.00 | 2026-06-04 | Initial release: three-tier storage + basic compress + FTS5 |

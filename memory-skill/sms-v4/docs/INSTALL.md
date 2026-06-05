# SMS v4 — Installation Guide

> One command install. Everything automatic.

---

## Quick Install (Recommended)

```bash
# Install everything in one command:
bash install.sh

# Or with custom memory directory:
bash install.sh --dir ~/my-sms-memory

This single command does ALL of the following automatically:
1. Installs npm dependencies
2. Creates blank memory directory structure
3. Generates CLAUDE.md with auto-recording rules
4. Registers MCP server in Claude Desktop/Code config
5. Ready to use immediately

---

## What Install Creates

~/sms-memory/                        ← memory directory
├── schema.json                      ← data format
├── fts/                             ← FTS5 search index (auto-created)
├── auto/raw/                        ← raw logs (permanent)
├── curated/                         ← consolidated.json (primary retrieval)
└── cache/                           ← hot tier cache

~/CLAUDE.md                          ← auto-recording rules for Claude Code

---

## Manual Installation

### Step 1: Install MCP Server

```bash
npm install

### Step 2: Configure Claude Code

Add to `~/.claude.json` (Linux/Mac) or `%APPDATA%\Claude\claude.json` (Windows):

```json
{
  "mcpServers": {
    "sms-v4-mcp": {
      "command": "node",
      "args": ["/path/to/sms-v4/server.js", "--dir", "/path/to/sms-memory"],
      "env": {
        "SMS_AUTHOR": "your-name"
      },
      "disabled": false,
      "autoApprove": [
        "search_fts", "search_memories", "write_or_merge",
        "hit_memory", "get_context", "get_stats"
      ]
    }
  }
}

For Windows users with WSL:

```json
{
  "mcpServers": {
    "sms-v4-mcp": {
      "command": "C:\\Windows\\System32\\wsl.exe",
      "args": [
        "node",
        "/path/to/sms-v4/server.js",
        "--dir", "/path/to/sms-memory"
      ],
      "env": { "SMS_AUTHOR": "your-name" }
    }
  }
}

### Step 3: Create CLAUDE.md

Copy `CLAUDE.md.template` to your home directory:

```bash
cp CLAUDE.md.template ~/CLAUDE.md

This enables automatic recording — Claude Code will remember things without being asked.

### Step 4: Restart Claude Code

Close and reopen Claude Code. Test with:

search_fts(query: "anything")
write_or_merge(type: "knowledge", summary: "Test entry")

---

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Node.js** | 18+ | For MCP server |
| **Python** | 3.8+ | For compress engine (optional but recommended) |
| **SQLite** | built-in | Python sqlite3 module (included) |
| **Claude Code** | latest | Or any MCP-compatible client |
| **OS** | Linux / macOS / Windows+WSL | |

---

## Verifying Installation

```bash
# Check tools are available
claude "list my MCP tools"

# Or call directly
search_fts(query: "test")
get_stats()

# Install complete if:
# 1. Tools listed ✅
# 2. search_fts returns 0 results (empty memory) ✅
# 3. Claude Code starts auto-recording ✅

---

## Next Steps

1. Start chatting with Claude Code normally
2. It will auto-record knowledge and preferences via CLAUDE.md rules
3. Run `compress.py` periodically to maintain the index
4. No manual cron needed — SMS v4 auto-compresses every 60s when idle, plus a full rebuild at midnight (system time).

```bash

---

## Uninstall

```bash
bash install.sh --uninstall
rm -rf ~/sms-memory
rm ~/CLAUDE.md

---

## Token Usage Measurement

SMS v4 includes a token counter tool to measure memory overhead.

### Install Tokenizer

```bash
# Local install (in sms-v4 directory)
npm install @anthropic-ai/tokenizer

# Or global install
npm install -g @anthropic-ai/tokenizer
```

### SMS v4 Baseline Token Overhead

The following measurements were taken with 32 entries and 4 days of data:

| Component | Tokens | When Loaded |
|-----------|--------|-------------|
| CLAUDE.md (auto-recording rules) | ~1,300 | Once per session start |
| Hot tier cache (top 20 entries) | ~130 | Every request |
| Consolidated.json (32 entries) | ~10,600 | Not auto-loaded, only on search |
| Single search_fts result | ~30 | On demand |

**Per-request overhead with SMS v4:** ~1,400 tokens (CLAUDE.md + Hot tier)

This means SMS adds about 50% to a typical Claude Code request (2-3K baseline).
The consolidated store is never injected into context — only search results are loaded on demand.

### How to Test on Your Machine

```bash
# Count tokens for your CLAUDE.md
node count_tokens.cjs --claude

# Count your current Hot tier cache
node count_tokens.cjs --hot

# Count your full memory store
node count_tokens.cjs --consolidated

# Get complete overview
node count_tokens.cjs --all
```

The `count_tokens.cjs` script is included in the sms-v4 directory.

### Understanding Your Results

- CLAUDE.md should be ~1,200-1,400 tokens (stable, depends on rules)
- Hot cache grows slowly as you accumulate high-score entries
- Consolidated grows with usage but is never auto-injected
- More entries = better recall, same per-request cost

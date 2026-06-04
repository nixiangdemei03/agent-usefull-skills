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

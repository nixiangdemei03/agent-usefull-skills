# SMS v1 — Architecture

> Version: 1.0 | Initial MCP bridge proof-of-concept

## Overview

SMS v1 is the simplest possible memory system: a Node.js MCP server that reads/writes JSON files on the local filesystem. No compression, no dedup, no search index.

## Components

| Component | File | Purpose |
|-----------|------|---------|
| MCP Server | `server.js` | Bridges Claude Code to local JSON files |
| Memory files | JSON files | Manual read/write via tools |

## Tools

- `search_memories` — Scan memory files by keyword
- `write_memory` — Write a new entry
- `get_context` — Get current context
- `get_stats` — Memory statistics

## Limitations

- No automatic dedup (manual management required)
- No compression (grows linearly with usage)
- No FTS5 full-text search
- All operations are manual

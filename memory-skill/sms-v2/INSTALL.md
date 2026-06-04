# SMS v2 — Installation Guide

## Quick Install

```bash
bash install.sh
```

## Manual MCP Configuration

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "sms-v2-mcp": {
      "command": "node",
      "args": ["/path/to/sms-v2/server.js", "--dir", "/path/to/memory"]
    }
  }
}
```

## Upgrade to v4

SMS v4 adds FTS5 search, auto-compress, and CLAUDE.md rules.
Install: `cd sms-v4 && bash install.sh`

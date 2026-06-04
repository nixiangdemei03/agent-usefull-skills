# SMS v3 — Installation Guide

## Quick Install

```bash
bash install.sh
```

## Manual MCP Configuration

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "sms-v3-mcp": {
      "command": "node",
      "args": ["/path/to/sms-v3/server.js", "--dir", "/path/to/memory"]
    }
  }
}
```

## Upgrade to v4

```bash
cd sms-v4
bash install.sh
```

v4 adds: FTS5 search, auto-compress (60s), CLAUDE.md rules, CJK boundary tokenization.

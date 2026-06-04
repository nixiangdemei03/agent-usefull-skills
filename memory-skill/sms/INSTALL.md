# SMS v1 — Installation Guide

## Quick Install

```bash
npm install
```

## Manual MCP Configuration

Add to `~/.claude.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sms-mcp": {
      "command": "node",
      "args": ["/path/to/sms-v1/server.js", "--dir", "/path/to/memory"]
    }
  }
}
```

## Notes

- v1 is a historical version. Use v4 for new installations.
- No automatic memory management — all operations are manual.

# SMS MCP Server

> Bridge between **Smart Memory System (SMS)** and **Claude Code** (or any MCP client).

Lets Claude Code read, search, and write to SMS structured memory — giving it persistent context across sessions.

## Quick Start

```bash
# 1. Install (auto-detects Claude Desktop and VS Code Claude)
./install.sh

# 2. Or with a custom memory directory
./install.sh --dir /path/to/ems-memory

# 3. Restart Claude Code
# 4. Start using:
```

## What You Get

### Resources (readable in Claude Code)

| URI | What |
|-----|------|
| `sms://index` | Master memory index |
| `sms://cache` | Current context cache |
| `sms://schema` | Memory schema & rules |
| `sms://skill` | SMS behavior guidelines |
| `sms://auto/2026-06-04` | Auto entries by date |
| `sms://curated/knowledge` | Curated long-term entries |

### Tools (callable from Claude Code)

| Tool | What it does |
|------|-------------|
| `search_memories(query, type, days_back, limit)` | Search memory with filters |
| `write_memory(type, summary, detail, tags, importance)` | Write a new memory entry |
| `get_context()` | Get current session context |
| `get_recent(limit)` | Get recent entries |
| `list_types()` | Available entry types |

## Install for Claude Code

The `install.sh` script automatically:
1. Installs npm dependencies
2. Registers the MCP server in Claude Desktop config
3. Registers in VS Code Claude extension config (if found)

### Manual config

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sms-mcp": {
      "command": "node",
      "args": ["/path/to/sms-mcp-server/server.js", "--dir", "/path/to/memory"],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Example: Using in Claude Code

```
Search my memories for "regex pitfalls"
→ Calls search_memories(query: "regex", type: "knowledge")

Read the context cache
→ Reads sms://cache

Write this down: I just learned about the MCP protocol
→ Calls write_memory(type: "knowledge", summary: "MCP protocol overview", ...)
```

## Architecture

```
┌──────────────────┐     stdio JSON-RPC     ┌─────────────────┐
│  Claude Code     │◄──────────────────────►│  sms-mcp-server  │
│  (or any MCP     │                        │  (server.js)     │
│   client)        │                        └────────┬─────────┘
└──────────────────┘                                  │
                                              ┌───────▼────────┐
                                              │  SMS Memory     │
                                              │  (JSON files)   │
                                              │  auto/          │
                                              │  curated/       │
                                              │  cache/         │
                                              └─────────────────┘
```

## Uninstall

```bash
./install.sh --uninstall
```

## Requirements

- Node.js 18+
- An existing SMS memory directory (or create one at the path you specify)

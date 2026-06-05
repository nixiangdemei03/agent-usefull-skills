# SMS v4

> FTS5 full-text search + auto-compress + CLAUDE.md auto-recording
> Current recommended version: **v4.04**

## Directory Structure

```
sms-v4/
├── README.md              ← this file
├── docs/                  ← documentation
│   ├── ARCHITECTURE.md    System architecture (EN/ZH)
│   ├── INSTALL.md         Installation guide (EN/ZH)
│   ├── MEMORY_SKILL.md    Agent behavior guide
│   ├── 版本优化详情.md     Version changelog
│   └── SMS_vs_Claude_     Comparison with claude-mem
├── install/               ← installation & code
│   ├── install.sh         One-click installer
│   ├── server.js          MCP server
│   ├── schema.json        Data format (v4.04)
│   ├── CLAUDE.md.template Auto-recording rules
│   ├── scripts/           compress.py, rebuild_fts.py, etc.
│   └── package.json       Dependencies
```

## Quick Start

```bash
bash install/install.sh
# Restart Claude Code
```

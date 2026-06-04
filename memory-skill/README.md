# Smart Memory System (SMS)

> 三层记忆系统 + FTS5 全文搜索。零费用。完全离线。

| 版本 | 路径 | 状态 |
|------|------|------|
| **v4 (latest)** | `sms-v4/` | **FTS5 + CJK 分词 + 全自动压缩** |
| v3 | `sms-v3/` | 三层架构基础版 |
| v2 | `sms-v2/` | fingerprint 去重 + hit_count |
| v1 | `sms/` | 初始 MCP 桥 |

## Quick Start

```bash
cd sms-v4
bash install.sh
# Restart Claude Code → done
```

## Documents

| 文件 | 说明 |
|------|------|
| `SMS_COMPLETE_OVERVIEW.md` | 总览 + claude-mem 对比 |
| `CLAUDE.md.template` | 自动记忆规则（安装时自动生成） |
| `sms-v4/ARCHITECTURE.md` | 架构详解（中英文） |
| `sms-v4/INSTALL.md` | 安装指南（中英文） |

## What's New in v4

- FTS5 full-text search with CJK/ASCII boundary tokenization
- Auto-compress every 60s when idle (>1min no activity)
- CLAUDE.md auto-recording rules (no manual commands needed)
- Zero cost compression (pure file ops, 0.2s per run)

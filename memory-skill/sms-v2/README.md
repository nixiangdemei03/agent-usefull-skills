# SMS v2 MCP Server

> Bridge between **Smart Memory System v2** and **Claude Code**.

SMS v2 核心特性：
- **写入前查重**：fingerprint 匹配 → 命中合并 / 不命中新建
- **命中考勤**：hit_count + last_hit → score 排序
- **三层分级**：Hot（~20条/自动加载）→ Warm（~100条/可检索）→ Cold

## Quick Start

```bash
# 安装依赖
cd ems-v2 && npm install

# 一键配置（自动识别 Claude Desktop + VS Code）
./install.sh

# 或指定 memory 目录
./install.sh --dir /path/to/my-memory

# 重启 Claude Code 即可使用
```

## What You Get

### Resources

| URI | Content |
|-----|---------|
| `sms://hot` | Hot 层前 20 条（按 score 排序） |
| `sms://cache` | 当前缓存（含 tier 统计） |
| `sms://schema` | v2 数据格式（fingerprint/score/tier） |
| `sms://stats` | 记忆系统统计 |
| `sms://auto/{date}` | 指定日期的记忆 |
| `sms://index` | 索引 |

### Tools

| Tool | v2 新特性 |
|------|-----------|
| `write_or_merge` | **写入前查重** ← 核心工具。自动 fingerprint → 合并或新建 |
| `hit_memory` | 按 id 手动标记命中（+hit_count、更新 score） |
| `search_memories` | 按 score 排序返回，支持 tier/tags 过滤 |
| `get_context` | 返回 Hot 层完整列表 |
| `get_stats` | tier 分布、top5 score |

## v2 → v1 关键变化

| | v1 | v2 |
|--|----|----|
| 写入策略 | 每次都新建 | **写入前查重 → 合并或新建** |
| 记忆膨胀 | 线性增长 | 合并后不增（一样的内容只占一行） |
| 排序 | 按时间 | **按 score = hit_count × recency** |
| 检索 | 搜全部 | **tier 感知：先 Hot → Warm → Cold** |
| 常用条目 | 不特殊处理 | **高 score 自动保留在 Hot 层** |
| 冷门条目 | 手动清理 | **自动降级到 Cold，不占 token** |

## Architecture

```
Claude Code ← stdio MCP → ems-v2-mcp (server.js)
                               │
                          ┌────▼────┐
                          │ memory/  │
                          │          │
                          │ auto/    │ ← 带 fingerprint + hit_count
                          │ cache/   │ ← Hot 层 20 条
                          │ curated/ │ ← 高 score 固化
                          └─────────┘
```

## Install for Claude Code

```bash
./install.sh
```

Or manually add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ems-v2-mcp": {
      "command": "node",
      "args": ["/path/to/ems-v2/server.js", "--dir", "/path/to/memory"],
      "disabled": false
    }
  }
}
```

# SMS v2 — 安装指南

## 快速安装

```bash
bash install.sh
```

## 手动配置 MCP

添加到 `~/.claude.json`：

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

## 升级到 v4

SMS v4 增加了 FTS5 搜索、自动压缩和 CLAUDE.md 规则。
安装：`cd sms-v4 && bash install.sh`

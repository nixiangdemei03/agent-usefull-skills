# SMS v3 — 安装指南

## 快速安装

```bash
bash install.sh
```

## 手动配置 MCP

添加到 `~/.claude.json`：

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

## 升级到 v4

```bash
cd sms-v4
bash install.sh
```

v4 新增：FTS5 搜索、60 秒自动压缩、CLAUDE.md 规则、CJK 分词。

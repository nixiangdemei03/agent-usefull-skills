# SMS v1 — 安装指南

## 快速安装

```bash
npm install
```

## 手动配置 MCP

添加到 `~/.claude.json` 或 `claude_desktop_config.json`：

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

## 注意

- v1 为历史版本。新装用户请使用 v4。
- 无自动记忆管理——所有操作需手动。

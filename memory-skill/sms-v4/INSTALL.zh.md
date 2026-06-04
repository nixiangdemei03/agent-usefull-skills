# SMS v4 — 安装指南

> 一键安装。全自动配置。

---

## 快速安装（推荐）

```bash
# 一键安装全部：
bash install.sh

# 或指定自定义记忆目录：
bash install.sh --dir ~/my-sms-memory
```

**这一个命令会自动完成以下所有操作：**
1. 安装 npm 依赖
2. 创建空白记忆目录结构
3. 生成 CLAUDE.md 自动记忆规则文件
4. 在 Claude Desktop/Code 中注册 MCP 服务器
5. 配置完成，即刻可用

---

## 安装后生成的文件

```
~/sms-memory/                        ← 记忆目录
├── schema.json                      ← 数据格式定义
├── fts/                             ← FTS5 搜索索引（自动生成）
├── auto/raw/                        ← raw 日志（永久）
├── curated/                         ← consolidated.json（主要检索文件）
└── cache/                           ← Hot 层缓存

~/CLAUDE.md                          ← Claude Code 自动记忆规则
```

---

## 手动安装

### 步骤 1：安装 MCP 服务器

```bash
npm install
```

### 步骤 2：配置 Claude Code

在 `~/.claude.json`（Linux/Mac）或 `%APPDATA%\Claude\claude.json`（Windows）中添加：

```json
{
  "mcpServers": {
    "sms-v4-mcp": {
      "command": "node",
      "args": ["/path/to/sms-v4/server.js", "--dir", "/path/to/sms-memory"],
      "env": {
        "SMS_AUTHOR": "你的名字"
      },
      "disabled": false,
      "autoApprove": [
        "search_fts", "search_memories", "write_or_merge",
        "hit_memory", "get_context", "get_stats"
      ]
    }
  }
}
```

Windows + WSL 用户：

```json
{
  "mcpServers": {
    "sms-v4-mcp": {
      "command": "C:\\Windows\\System32\\wsl.exe",
      "args": [
        "node",
        "/path/to/sms-v4/server.js",
        "--dir", "/path/to/sms-memory"
      ],
      "env": { "SMS_AUTHOR": "你的名字" }
    }
  }
}
```

### 步骤 3：创建 CLAUDE.md

将 `CLAUDE.md.template` 复制到用户主目录：

```bash
cp CLAUDE.md.template ~/CLAUDE.md
```

这会开启自动记录功能 —— Claude Code 会主动记住重要信息，无需手动指令。

### 步骤 4：重启 Claude Code

关闭并重新打开 Claude Code。测试验证：

```
search_fts(query: "anything")
write_or_merge(type: "knowledge", summary: "测试条目")
```

---

## 系统要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| **Node.js** | 18+ | MCP 服务运行环境 |
| **Python** | 3.8+ | 压缩引擎（可选但推荐） |
| **SQLite** | 内置 | Python sqlite3 模块（已包含） |
| **Claude Code** | 最新版 | 或任何支持 MCP 的客户端 |
| **操作系统** | Linux / macOS / Windows+WSL | |

---

## 验证安装

```bash
# 检查工具是否可用
claude "列出我的 MCP 工具"

# 或直接调用
search_fts(query: "test")
get_stats()

# 安装成功标志：
# 1. 工具列表正确显示 ✅
# 2. search_fts 返回 0 条（空白记忆） ✅
# 3. Claude Code 开始自动记录 ✅
```

---

## 下一步

1. 正常与 Claude Code 对话即可
2. 它会通过 CLAUDE.md 规则自动记录知识和偏好
3. 定期运行 `compress.py` 维护索引
4. 无需手动设置 cron — SMS v4 每 60 秒自动检查，闲置时自动压缩，并在午夜（系统时间 00:00）执行全量重建。

```bash
```

---

## 卸载

```bash
bash install.sh --uninstall
rm -rf ~/sms-memory
rm ~/CLAUDE.md
```

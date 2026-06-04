# SMS v4 — 架构文档

> Smart Memory System v4
> 面向 AI Agent 的三层本地记忆系统，集成 FTS5 全文搜索。

---

## 概述

SMS 是一个持久化记忆系统，专为 AI Agent（Claude Code、OpenClaw、Gemini CLI 等）设计。
记忆以 JSON 文件存储，通过 SQLite FTS5 提供快速全文搜索。

**核心设计原则：**
- 纯本地 —— 无云服务、无 API、无向量数据库
- 人类可读 —— 所有数据是 JSON，记事本即可查看
- Git 友好 —— JSON diff/merge，支持团队协作
- 零费用压缩 —— 无需 LLM 调用即可完成维护

---

## 三层架构

```
┌──────────────────────────────────────────────────────────────┐
│                    🥇 CONSOLIDATED                            │
│                   curated/consolidated.json                   │
│          所有条目：fingerprint 去重合并，按 score 排序          │
│          Hot（20 条）→ 高分，完整 detail                       │
│          Cold（其余）→ title_only + source 指针                  │
│          最高优先级检索目标                                      │
├──────────────────────────────────────────────────────────────┤
│                    🥈 每日文件                                 │
│                   auto/YYYY-MM-DD.json                        │
│          每天的完整 detail 条目                                │
│          含 tags、context、author、contributors                │
│          次优先级检索目标                                        │
├──────────────────────────────────────────────────────────────┤
│                    🥉 RAW 日志                                │
│                  auto/raw/YYYY-MM-DD.raw.json                 │
│          最小格式（约 50 字节/条）                              │
│          永不删除 —— 永久审计追踪                              │
├──────────────────────────────────────────────────────────────┤
│                    ⚡ FTS5 搜索索引                           │
│                    fts/memory.db                              │
│          SQLite FTS5 全文搜索                                  │
│          每次 compress 时自动重建                              │
│          中英文混合文本自动分词                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 数据流

```
对话产生知识点
         │
         ├─→ auto/raw/*.raw.json   ← 最小日志（50B，永不删）
         │
         ├─→ auto/*.json            ← 完整 detail + tags
         │
         └─→ compress.py 触发
                  │
                  ├─ 1. dirty check（stat 比较，0.001s 跳过）
                  ├─ 2. 读取 raw + auto + 上一次 consolidated
                  ├─ 3. fingerprint 分组 → 去重合并
                  ├─ 4. score = hit_count × recency
                  ├─ 5. 分配层级（hot/warm/cold）
                  ├─ 6. 冷门条目 → title_only
                  ├─ 7. 写 consolidated.json
                  └─ 8. 重建 FTS5 索引
```

---

## 计分公式

```
score = hit_count × recency_factor

recency_factor:
  < 1 天 → 3.0    （刚提到）
  < 7 天 → 1.5    （本周）
  < 30 天 → 1.0   （本月）
  更久   → 0.5    （很久以前）
```

### 层级

| 层级 | Score | 上限 | 会话行为 |
|------|-------|------|---------|
| 🔥 hot | ≥ 8 | 20 | 自动注入 system prompt |
| ☀️ warm | ≥ 3 | 100 | 可检索，不自动加载 |
| ❄️ cold | < 3 | ∞ | 仅保留 title，detail 通过 raw 回溯 |
| 🗑️ archive | — | — | 知识已迁移到外部文档 |

---

## Title Only 压缩

冷门条目自动压缩为仅保留标题（约 100 字节 vs 原约 500 字节）：

```json
// 冷门条目（title_only）
{
  "summary": "用户习惯用什么称呼",
  "title_only": true,
  "source_raw": "auto/raw/2026-06-04.raw.json",
  "score": 1.5
}
```

title 本身就能回答大部分问题。需要完整 detail 时，按 fingerprint 回溯 raw 日志。

---

## Fingerprint 去重

`fingerprint = sorted(tags).join(',') + '|' + summary[0:50].lower()`

相同 fingerprint = 同一知识点 → compress 时自动合并：
- hit_count 累加
- contributors 自动合并
- detail 按 author 前缀合并
- score 重新计算

---

## FTS5 搜索

SQLite FTS5 全文索引，自动处理中英文混排分词：

```
原文:  "Q2用pipe chain实现'AA before BB'"
处理后: "Q2 用 pipe chain 实现'AA before BB'"
```

可以搜 "pipe"、"chain"、"grep" 等关键词，即使它们紧邻中文字符。

| 搜索方式 | 工具 | 速度 | 模糊度 |
|---------|------|------|--------|
| fingerprint 精确 | write_or_merge | 瞬间 | 精确 |
| 字段搜索 | search_memories | ~50ms | 否 |
| **FTS5 全文搜索** | **search_fts** | **~5ms** | **支持（BM25 排序）** |

---

## MCP 服务工具

| 工具 | 说明 |
|------|------|
| `search_fts` | FTS5 全文搜索，模糊匹配，BM25 相关性排序 |
| `search_memories` | 传统 tag/type/关键词搜索 |
| `write_or_merge` | 写入新条目，自动 fingerprint 去重 |
| `hit_memory` | 标记条目被引用（增加 score） |
| `get_context` | 获取当前 Hot 层上下文 |
| `get_stats` | 系统统计和层级分布 |

---

## 文件结构

```
sms-memory/                      ← 安装时可配置
├── schema.json                  ← 数据格式定义
├── fts/
│   └── memory.db                ← SQLite FTS5 搜索索引
├── auto/
│   ├── raw/                     ← 最小 raw 日志（永不删除）
│   └── YYYY-MM-DD.json          ← 每日完整条目
├── curated/
│   └── consolidated.json        ← 最高优先级检索目标
├── cache/
│   └── memory_cache.json        ← Hot 层上下文缓存
└── scripts/
    ├── compress.py              ← 主压缩引擎
    ├── rebuild_fts.py           ← FTS5 索引构建器
    ├── consolidate.sh           ← Shell 合并封装
    ├── cache_refresh.sh         ← 缓存更新
    └── _summary.py              ← 层级摘要助手
```

---

## SMS v4 vs claude-mem 对比

| 维度 | claude-mem | SMS v4 |
|------|-----------|--------|
| 存储 | SQLite + Chroma 向量库 | **JSON + SQLite FTS5** |
| 压缩 | LLM 语义摘要（秒级） | **文件 stat + 合并（毫秒级）** |
| 搜索 | 向量语义 | **FTS5 全文搜索（精确 + 模糊）** |
| Token 消耗 | ~26,800t/天 | **~1,660t/天** |
| 离线 | ❌ 依赖 Chroma 服务 | ✅ **完全离线** |
| 人类可读 | ❌ 二进制向量 | ✅ **cat 任意 JSON** |
| Git 协作 | ❌ 不支持 | ✅ **JSON diff/merge** |
| 压缩 500 条 | ~30-60 秒 | **~0.2 秒** |
| 依赖 | Chroma + SQLite + Node | **Node.js + Python3 即可** |
| 数据控制权 | Anthropic 服务器 | **你的本地文件系统** |

---

## 自动化运行

SMS v4 全自动运行，无需任何手动干预：

### 每分钟（60 秒 cron）
```
每 60 秒 → compress.py --auto
  ├─ 上次压缩 < 60 秒前？ → 跳过（防重复）
  ├─ 有新数据吗？         → 跳过（dirty check，0.001s）
  └─ 有新数据 + 闲置 >60 秒 → 全量压缩（0.2s）
       ├─ fingerprint 去重合并
       ├─ score 重算
       ├─ title_only 降级
       ├─ 写 consolidated.json
       ├─ 重建 FTS5 索引
       └─ 更新 .last_compress 锁
```

### 每日凌晨于本地系统时间执行 — 各时区自动适配
```
强制全量压缩，确保 FTS5 索引每日至少重建一次。
```

### CLAUDE.md（自动记录）
安装时自动生成。Claude Code 按照以下规则工作：
- 发现新知识/偏好/决策/失败时自动调用 `write_or_merge`
- 回答历史问题前自动调用 `search_fts`
- 自动过滤打招呼、确认、噪音
- 无需用户指令，后台静默运行

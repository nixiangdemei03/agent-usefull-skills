# SMS v4 — 架构文档

> 智能记忆系统 v4.05
> 三层本地记忆系统，支持自动压缩与 supersedes 感知搜索。

---

## 概览

SMS 是为 AI 代理（Claude Code、OpenClaw、Gemini CLI 等）设计的持久化记忆系统。
以 JSON 文件存储结构化记忆，通过 SQLite FTS5 提供快速全文搜索，
并根据重要性、最近使用频率、命中次数自动压缩/降级记忆。

**设计原则：**
- 纯本地 — 无云端、无 API、无向量数据库
- 人类可读 — 所有数据为 JSON，记事本即可查看
- Git 友好 — JSON diff/merge 支持团队协作
- 零成本压缩 — 维护过程不消耗 LLM token
- 自动化 — 闲时检测 + 定时压缩 + 交换式降级

**当前版本：v4.05**

---

## 三层存储架构

```
┌──────────────────────────────────────────────────────────────┐
│                    🥇 CONSOLIDATED                           │
│                   curated/consolidated.json                   │
│          所有条目：fingerprint 去重合并，按 score 排序        │
│                                                                  │
│          🔥 Hot  (上限 20)  → 高评分，全量 detail            │
│              每次会话自动注入上下文                              │
│                                                                  │
│          ☀️ Warm (上限 100) → 中等评分，全量 detail           │
│              搜索可见，不自动加载                                │
│                                                                  │
│          ❄️ Cold (无上限)    → title_only + SQLite 指针        │
│              detail 存入 fts/memory.db，O(1) 检索              │
│              被 superseded 的条目压缩时强制送入 cold             │
│                                                                  │
│          优先查询目标                                            │
├──────────────────────────────────────────────────────────────┤
│                    🥈 日文件                                   │
│                   auto/YYYY-MM-DD.json                        │
│          每天的全量 detail 条目                                │
│          含 tags、context、author、contributors                │
│          次级查询目标                                          │
├──────────────────────────────────────────────────────────────┤
│                    🥉 原始日志                                 │
│                  auto/raw/YYYY-MM-DD.raw.json                 │
│          最小格式（~50 bytes/条）                              │
│          永不删除 — 永久审计追踪                               │
├──────────────────────────────────────────────────────────────┤
│                    ⚡ FTS5 搜索索引                            │
│                    fts/memory.db                              │
│          SQLite FTS5 全文搜索                                  │
│          Supersedes 感知：默认过滤旧条目                        │
│          中英文边界分词，支持混合语言搜索                       │
└──────────────────────────────────────────────────────────────┘
```

---

## 评分公式

```
Score = I × e^(-λt) × log(1 + f)

I = 重要性 (1-10 分，写入时必传)
λ = ln(2) / 21  (半衰期 = 21 天，单一连续 λ)
t = 距离上次命中的天数
f = 命中次数
```

活性标签（纯文本标记，非多个 λ 值）：
| 时段 | 标签 |
|------|------|
| < 14 天 | 🔥 高活跃 |
| 14-28 天 | ☀️ 中活跃 |
| 28-42 天 | 🌥️ 低活跃 |
| > 42 天 | 🌙 弱活跃 |

### Superseded 惩罚

标记为 `superseded: true` 的条目在每次压缩时**强制进入 Cold 层**，忽略评分。
腾出的 Hot/Warm 位置立即由下一顺位的最高分有效条目填补。

---

## 数据流

```
对话产生知识点
         │
         ├─→ auto/raw/*.raw.json   ← 最小日志（50B，永不删除）
         │
         ├─→ auto/*.json            ← 完整 detail + tags
         │
         └─→ compress.py 触发
                  │
                  ├─ 1. 脏检查（stat mtime，0.001s 跳过）
                  ├─ 2. 读取 raw + auto + 上次 consolidated
                  ├─ 3. fingerprint 分组 → 去重合并
                  ├─ 4. score = I × e^(-λt) × log(f+1)
                  ├─ 5. 交换式降级（Hot↔Warm↔Cold，数量对等）
                  ├─ 6. 强制：superseded → Cold，重填 Hot/Warm
                  ├─ 7. Cold 条目 title_only 压缩
                  ├─ 8. Cold detail → SQLite memories 表
                  ├─ 9. 写入 consolidated.json
                  └─ 10. 重建 FTS5 索引
```

### 压缩触发

| 触发方式 | 条件 | 行为 |
|---------|------|------|
| **闲时** | Windows 用户空闲 >5 分钟（GetLastInputInfo）+ 6 次连续确认 | 有新内容→压缩。无新内容→跳过 |
| **定时** | 每天系统 00:00 | 全量压缩 + 交换降级 + FTS5 重建 |

---

## 交换式降级

```
压缩前：
  Hot (20)         Warm (N)         Cold (∞)

重算评分后：
  Hot-bottom → Warm-front  （Hot 中评分最低的条目）
  Warm-bottom → Cold       （数量 = Hot→Warm 的数量）
  
  Warm 饱和度 < 90%？ → 抑制 Cold 降级
  Warm 超 100？       → 先接受溢出，逐步消化
```

核心规则：**降级数量 = 升级数量**，不浪费层级名额，不产生溢出尖峰。

---

## Supersedes 机制

当新知识取代旧知识时（如改名 "NS5" → "Elio"）：

```
write_or_merge(
  summary="我的名字是 Elio",
  importance=10,
  supersedes=["mem-旧名字的ID"]
)
```

### 效果

| 搜索方式 | 默认行为 | 历史查询 |
|---------|---------|---------|
| `search_memories` | 只返回活跃（非 superseded）条目 | 检测"以前"/"之前"关键词→全部显示 |
| `search_fts` | 过滤 superseded 条目 | 同上，由历史关键词触发 |
| `get_context` | 仅活跃条目 | — |
| `compress.py` | 强制 superseded → cold + title_only | — |
| `update_entry` | 可恢复：`tier="hot"` 即可还原 | — |

历史关键词：以前、之前、原来、以前叫什么、几月几号、previous、old name 等。
结果按 `supersedes_index DESC` 排序（最新优先）。

---

## Fingerprint 去重

**v4.03+**：`fingerprint = summary.trim().slice(0,50).toLowerCase()`

不再包含 tags。向后兼容：查询时同时匹配旧格式（`tags|summary`）和新格式（纯 summary）。

相同 fingerprint = 相同知识 → 压缩时自动合并：
- hit_count 累加
- contributors 去重合并
- detail 按来源拼接
- score 重新计算

---

## FTS5 搜索

SQLite FTS5 全文搜索，中英文边界自动分词：

```
原文： "Q2用pipe chain实现'AA before BB'"
分词后："Q2 用 pipe chain 实现'AA before BB'"
```

**Supersedes 过滤：**
```sql
WHERE memories_fts MATCH ?
  AND (m.superseded IS NULL OR m.superseded = 0)
```

搜索方式：
| 方法 | 工具 | 速度 | 模糊 | Supersedes 感知 |
|------|------|------|------|----------------|
| fingerprint 精确 | write_or_merge | 即时 | 精确 | ✅ |
| 精确匹配 | search_memories | ~50ms | 否 | ✅ |
| **全文搜索** | **search_fts** | **~5ms** | **是 (FTS5 BM25)** | ✅ |
| LIKE 降级 | search_fts | ~50ms | 是 | ✅ |

---

## MCP 服务端工具（v4.05）

| 工具 | 说明 |
|------|------|
| `search_fts` | FTS5 全文搜索，模糊匹配，BM25 排序，supersedes 感知 |
| `search_memories` | 按 tag/type/keyword 搜索，支持历史查询模式 |
| `write_or_merge` | 写入新条目，fingerprint 去重 **必传 importance**，可选 supersedes |
| `hit_memory` | 标记条目被引用。三路回写：auto→consolidated→SQLite |
| `get_context` | 获取当前 Hot 层上下文（实时聚合，无静态缓存） |
| `get_stats` | 系统统计，互斥 tier 分类 |
| `recalc_score` | 按新公式重算单条或全量条目评分 |
| `update_entry` | 直接修改 tier、importance 或 supersedes 状态 |

---

## 闲时检测

```
Windows 侧 (idle-detect.ps1)：
  GetLastInputInfo → 每 10s → 写入 .claude/idle_state.txt

WSL/压缩侧 (compress.py --auto)：
  读取 idle_state.txt → 连续 6 次空闲（>5 min）→ 触发压缩
  备选：直接调 PowerShell 若文件不可用
  无法检测空闲 → 跳过压缩
```

---

## 文件结构（v4.05）

```
sms-v4/
├── README.md              ← 概览
├── docs/                  ← 文档
│   ├── ARCHITECTURE.md    架构说明（英文）
│   ├── ARCHITECTURE.zh.md 架构说明（中文）
│   ├── INSTALL.md         安装指南（英文/中文）
│   ├── MEMORY_SKILL.md    Agent 行为指南
│   ├── 版本优化详情.md     版本更新日志
│   └── SMS_vs_Claude_     与 claude-mem 对比
├── install/               ← 安装与代码
│   ├── install.sh         一键安装脚本
│   ├── server.js          MCP 服务器
│   ├── schema.json        数据格式定义（v4.05）
│   ├── CLAUDE.md.template 自动记录规则
│   ├── scripts/           compress.py、rebuild_fts.py 等
│   └── package.json       依赖
```

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| **v4.05** | 2026-06-05 | Superseded 强制→Cold + Hot 重填 |
| v4.04 | 2026-06-05 | FTS5 supersedes 过滤 + SQLite 列补齐 |
| v4.03 | 2026-06-05 | Supersedes 机制 + 历史查询 + 7 项 bug 修复 |
| v4.02 | 2026-06-05 | MCP 工具扩展 + idle-detect.ps1 |
| v4.01 | 2026-06-05 | 压缩引擎 v3：新评分、交换降级、SQLite cold |
| v4.00 | 2026-06-04 | 初始发布：三层存储 + 基础压缩 + FTS5 |

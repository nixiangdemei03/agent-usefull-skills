# 🧠 Smart Memory System v3

> SMS v3 — 三层架构：全量 raw 日志 → 日去重 → 跨天压缩
> Hot 层恒定 ≤20 条，cold 条目自动降为 title_only

---

## 三层存储

```
auto/raw/2026-06-04.raw.json    ← 🥉 全量最小格式日志（50B/条，只增不改）
auto/2026-06-04.json             ← 🥈 当天去重完整条目（500B/条）
curated/consolidated.json       ← 🥇 跨天压缩记忆（高频全量 + 低频 title_only）
```

### 🥉 Raw 日志

每次知识捕获的同时写入 raw 日志，最小格式：

```json
{"t":"12:00","s":"grep pipe 必须加 ()","tp":"knowledge","fp":"regex,grep|grep pipe 必须加 ()"}
```

- 字段名压缩：`t`=时间，`s`=title，`tp`=类型，`fp`=fingerprint
- **只增不改**——永不修改、永不删除
- 格式极轻：~50-100 bytes/条，一年 <1MB

### 🥈 日去重文件

上轮 compress 后自动清空重建。daily 文件中的每条信息在 raw 中都有对应。

### 🥇 Consolidated（最高优先级）

跨天按 fingerprint 去重合并后的压缩结果。检索时**优先查 consolidated**。

冷门条目自动降为 title_only：

```json
{
  "summary": "从 CSE SSH 切换到 COMP9044",
  "title_only": true,
  "source_raw": "auto/raw/2026-06-04.raw.json",
  "score": 1.5,
  "tier": "cold"
}
```

title 本身就能回答大部分问题。需要细节时按 `fingerprint` 回溯 raw 日志。

---

## 检索优先级

```
🥇 查 consolidated.json      ← 高频全量 / 低频 title 都在这里
  ├─ 命中，非 title_only → 返回完整 detail（~70 tokens）
  ├─ 命中，title_only     → title 本身已能回答
  │   └─ 需要细节 → 按 fingerprint 回溯 raw 日志
  └─ 未命中
       ↓
🥈 查 auto/YYYY-MM-DD.json    ← 当天的去重完整条目
       ↓
🥉 查 auto/raw/*.raw.json     ← 全量日志（永不丢失）
```

---

## 压缩流程

```
对话结束
  │
  ├─ 写 ongoing 条目到 auto/ + raw/
  │
  ▼
compress.py 触发
  │
  ├─ 🔍 dirty check：consolidated 是否最新？
  │    ├─ 是 → 跳过（0.001s）
  │    └─ 否 → 继续
  │
  ├─ 读 raw/ 日志 → fingerprint 分组
  ├─ 跨天去重合并 → 重算 score
  ├─ 高频全量、低频 title_only
  ├─ 写 consolidated.json
  ├─ 清空 auto/（信息已入 consolidated + raw）
  └─ 完成（~0.2s）
```

每次 compress 前先做 dirty check：比 consolidated 和所有 auto/raw 文件的修改时间。
如果 consolidated 已是最新，直接跳过，0 操作。

---

## entry 类型（v3 新增）

| 类型 | 压缩策略 | 说明 |
|------|---------|------|
| `knowledge` | 尽量全量 | 知识点 |
| `decision` | 尽量全量 | 决策 + 理由 |
| `insight` | 尽量全量 | 跨 session 模式发现 |
| `failure` | 尽量全量 | 失败案例 + 教训 |
| `preference` | 默认 title_only | 偏好一句话就说清了 |
| `event` | 默认 title_only | 事件时间线 |
| `context_switch` | 默认 title_only | 上下文切换记录 |
| `chat` | title_only | 闲聊留下的有用片段 |
| `chat_insight` | title_only | 闲聊中意外发现的洞察 |

全量类型即使 score 低也可能保留 detail，高频 title_only 类型（hit_count ≥ 5）也会升级为全量。

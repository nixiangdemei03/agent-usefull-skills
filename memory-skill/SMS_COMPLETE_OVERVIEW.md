# SMS COMPLETE OVERVIEW — Smart Memory System

> 为 AI Agent 设计的持久记忆系统。
> 解决"每次会话都失忆"的问题——让 Agent 记住该记住的，忘掉该忘掉的。

---

## What Is SMS

一套**纯文件化的记忆架构**，不依赖任何外部服务（向量库、数据库、LLM 运行时），
只依赖 JSON 文件和一套压缩脚本。完全离线运行，零额外费用。

| 依赖 | 用途 | 可选？ |
|------|------|--------|
| Node.js 18+ | MCP 服务器 | ✅ 只用 compress.py 则不需要 |
| Python 3.8+ | compress 引擎 | ✅ 只用 MCP 检索则不需要 |
| SQLite | FTS5 搜索 | 内置在 Python 中 |

---

## Version History

| 版本 | 新特性 |
|------|--------|
| **v4** (latest) | FTS5 全文搜索 + CJK/ASCII 分词 + 全自动压缩 + CLAUDE.md 规则 |
| v3 | 三层架构（raw/日文件/consolidated）+ title_only 压缩 |
| v2 | fingerprint 去重 + hit_count 计分 + score 排序 |
| v1 | 初始 MCP 桥，纯手动 |

---

## Token Economy — 为什么 SMS 省钱

token 开销 = 钱。以下是三者对比。

### Baseline: Per-Request Overhead

| 开销项目 | Claude 原生记忆 | claude-mem | SMS v4 |
|---------|---------------|-----------|--------|
| 会话启动（固定） | ~500-2,000t | ~1,500-2,500t | **~1,430t** |
| 每次搜索返回 | 无搜索功能 | ~2,500t (top-5 obs) | **~27t** (1 条结果) |
| 存储压缩 | 免费（服务端） | LLM 摘要（30-60s） | **零**（文件操作 0.2s） |
| 向量库费用 | 无 | Chroma 服务器 | **零** |

### Measured SMS v4 Breakdown

以下数据基于真实测量（32 条记忆，4 天数据）：

| 组件 | Token | 何时加载 |
|------|-------|---------|
| CLAUDE.md（自动记忆规则） | ~1,300t | 每**会话**一次 |
| Hot 层 20 条 | ~130t | 每**请求** |
| Consolidated 全量（32 条） | ~10,600t | **不加载**，仅搜索时命中 |
| 单次搜索命中 | ~27t | 按需 |

### Per-Session Cost Comparison

| | Claude 原生记忆 | claude-mem | SMS v4 |
|---|---------------|-----------|--------|
| 会话启动 | ~1,200t avg | ~2,000t avg | **~1,430t** |
| 搜索 5 次 | 无此功能 | ~12,500t (5×2,500) | **~135t** (5×27) |
| 自动记录 | 免费（Anthropic 端） | ~500t/次（LLM 压缩） | **~130t**（Hot 层固定） |
| 日总计（10 会话+20 搜索） | ~12,000t | **~85,000t** | **~14,830t** |

### Monthly Cost ($3/M tokens)

| | Claude 原生记忆 | claude-mem | SMS v4 |
|---|---------------|-----------|--------|
| 月 token 总量 | ~360K | ~2,550K | **~445K** |
| 月费用 | **$1.08** (免费额度内) | **$7.65** | **$1.34** |
| 年费用 | **$12.96** | **$91.80** | **$16.08** |

**claude-mem 贵 5.7 倍的原因：**
1. 每次搜索返回 top-5 完整 obs（2,500t），SMS 只返回 1 条 title（27t）
2. 每次压缩调用 LLM 做摘要，SMS 什么都不调
3. 向量库 Chroma 需要额外服务器

**Claude 原生记忆便宜但功能受限：**
- 只记简单事实（"用户叫 Alice"），记不了结构化知识点
- 无搜索功能
- 数据在 Anthropic 服务器上，不可控

---

## Full Comparison Tables

### Architecture

| 特性 | claude-mem | SMS v1 | SMS v2 | SMS v3 | SMS v4 |
|------|-----------|--------|--------|--------|--------|
| 捕获方式 | 系统钩子全量 | 手动写文件 | 实时判断 | 全量 raw+分级 | **全量 raw+FTS5** |
| 存储引擎 | SQLite+Chroma | 纯 JSON | 纯 JSON | 三层 JSON | **JSON+FTS5** |
| 检索 | 向量语义 | 无 | fingerprint | fingerprint+raw | **fingerprint+FTS5** |
| 压缩 | LLM（秒级） | 无 | hit_count 排序 | 文件操作(毫秒) | **文件操作(毫秒)** |
| 离线 | ❌ | ✅ | ✅ | ✅ | ✅ |
| 可读 | ❌ 二进制 | ✅ cat | ✅ cat | ✅ cat | ✅ **cat+SQL** |
| Git 协作 | ❌ | ❌ | ✅ | ✅ | ✅ |
| 模糊搜索 | ✅ 向量 | ❌ | ❌ | ⚠️ title | **✅ FTS5** |
| 自动压缩 | ❌ | ❌ | ❌ | ❌ | **✅ 60s cron** |
| CLAUDE.md | ❌ | ❌ | ❌ | ❌ | **✅ 自动记录** |

### Performance

| 指标 | claude-mem | SMS v4 |
|------|-----------|--------|
| 压缩 500 条 | ~30-60s (LLM) | **~0.2s** (文件操作) |
| 单次搜索 token | ~2,500t | **~27t** |
| 年存储 | ~4MB | **~1MB** (含 raw) |
| 搜索速度 | 向量 ~50ms | **FTS5 ~5ms** |
| 运行依赖 | Chroma+SQLite+Node | **Node+Python3** |

### Pros & Cons

| 系统 | ✅ 优点 | ❌ 缺点 |
|------|--------|--------|
| **claude-mem** | 全量捕获，什么都记；模糊回忆强 | 依赖向量库，不可离线；token 消耗大；压缩慢；费用高 |
| **SMS v1** | 零依赖，纯文件 | 无去重、无搜索、无压缩 |
| **SMS v2** | fingerprint 去重；零依赖；token 恒定 | 无全量保底；冷门条目丢失 |
| **SMS v3** | 三层存储；title_only 压缩；Git 协作 | 无 FTS5；无自动压缩 |
| **SMS v4** | FTS5 搜索 + 自动压缩 + CLAUDE.md 规则 + 零费用 | FTS5 需 SQLite（Python 内置） |

### Garbage Filtering — CCTV vs Notebook

| 场景 | claude-mem（防漏） | SMS v4（防脏） |
|------|-------------------|--------------|
| 核心理念 | 全量→AI 压缩 | **raw 全量 + consolidated 精筛** |
| 闲聊中有用的信息 | 进 obs→可能漏 | **即时判断，有价值才进 consolidated** |
| 三个月后的重要片段 | LLM 可能没发现，但 obs 还在 | **raw 日志永远在** |
| 一句话总结 | **CCTV 监控** — 90% 垃圾 | **助理笔记** — 干净精炼 |

---

## Cost Comparison Summary

```
                 Claude 原生    claude-mem      SMS v4
                 记忆
                ──────────    ──────────      ──────────
月 token  ~360K         ~2,550K         ~445K
月费用       $1.08          $7.65           $1.34
年费用       $12.96         $91.80          $16.08
离线         ❌             ❌              ✅
数据控制     Anthropic      本地(需Chroma)  本地(纯文件)
搜索精度     无             向量模糊        精确+FTS5
```

## Recommendation

| 你是…… | 选 |
|--------|-----|
| 不想折腾 | Claude 原生记忆 |
| 什么都想回忆 | claude-mem（愿意付费） |
| **省钱+可控+离线** | **SMS v4** |
| 团队协作 | **SMS v4** |
| 数据分析/审计 | **SMS v4** |

---

*Last updated: 2026-06-04*

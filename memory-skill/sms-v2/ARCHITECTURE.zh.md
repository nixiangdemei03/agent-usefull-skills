# SMS v2 — 架构

> 版本: 2.0 | 引入了 fingerprint 去重 + hit_count 计分

## 概述

SMS v2 通过 fingerprint 匹配实现自动去重。每条条目由 tags + summary 前缀生成唯一 fingerprint。写入时遇到相同 fingerprint 的条目会自动合并（hit_count 递增）而非重复。

## 核心特性

| 特性 | 说明 |
|------|------|
| Fingerprint 去重 | `fingerprint = sorted(tags) + '|' + summary[:50].lower()` |
| hit_count 追踪 | 每次合并 +1 |
| score 计算 | `score = hit_count × recency_factor` |
| 自动分级 | hot (score ≥8, 上限 20), warm (≥3, 上限 100), cold (<3) |

## 与 v4 的差距

- 无 FTS5 全文搜索
- 无 CJK/ASCII 分词
- 无 raw 日志永久存储
- 无自动压缩定时任务
- 无 CLAUDE.md 自动记录规则

# SMS v3 — 架构

> 版本: 3.0 | 三层记忆：raw 日志 → 日文件 → consolidated

## 概述

SMS v3 引入了三层存储结构，这是 v4 的基础。增加了 raw 日志永久存储、每日去重文件和跨天压缩。

## 三层存储

```
🥉 auto/raw/YYYY-MM-DD.raw.json   ← 最小格式（~50B/条，永不删除）
🥈 auto/YYYY-MM-DD.json            ← 完整 detail 条目含 tags
🥇 curated/consolidated.json       ← fingerprint 合并，score 排序，title_only 压缩
```

## v3 新特性

| 特性 | 说明 |
|------|------|
| Raw 日志 | 最小格式永久审计追踪 |
| 日文件 | 每日完整 detail 含 tags |
| Consolidated | 跨天去重合并 |
| Dirty check | 无变化时跳过（0.001s） |
| Title only | 冷门条目压缩至 ~100 字节 |
| Git 同步 | JSON diff/merge 团队协作 |

## 与 v4 的差距

- 无 FTS5 全文搜索
- 无 CJK/ASCII 分词
- 无自动压缩定时任务
- 无 CLAUDE.md 自动记录规则

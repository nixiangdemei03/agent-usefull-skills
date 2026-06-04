# SMS v3 — 架构

> 三层记忆：raw 日志 → 日文件 → consolidated。当前系统的基础。

## 三层结构
- 🥉 raw/: 最小格式日志（~50B/条，永不删除）
- 🥈 auto/*.json: 每日完整条目（含 tags）
- 🥇 curated/consolidated.json: fingerprint 合并，score 排序，title_only 压缩

## 计分
`score = hit_count × recency_factor`

## 压缩
纯文件操作，无需云服务（500 条约 0.2 秒）。

# SMS v2 — 架构

> 引入了 fingerprint 去重 + hit_count 计分。尚未实现三层架构。

核心特性：
- 基于 fingerprint 的写入去重
- hit_count 高频命中追踪
- 基于 score 的排序

#!/usr/bin/env node
/**
 * EMS v2 MCP Server — Elio Memory System × Claude Code Bridge
 *
 * v2 新特性:
 * 1. write_or_merge: 写入前查 fingerprint，命中则合并
 * 2. hit_count / last_hit 追踪
 * 3. score-based 搜索排序
 * 4. hot/warm/cold tier-aware 查询
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
  ListResourceTemplatesRequestSchema,
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { readFileSync, existsSync, writeFileSync, readdirSync, statSync, mkdirSync } from "fs";
import { join, resolve, sep } from "path";
import { fileURLToPath } from "url";
import Database from "better-sqlite3";

// ── Config ──

const args = process.argv.slice(2);
const dirIdx = args.indexOf("--dir");
const MEMORY_DIR = resolve(
  dirIdx !== -1 && args[dirIdx + 1]
    ? args[dirIdx + 1]
    : process.env.EMS_MEMORY_DIR
      ? process.env.EMS_MEMORY_DIR
      : join(process.cwd(), "memory")
);

const SERVER_NAME = "sms-v4-mcp";
const FTS_DB = join(MEMORY_DIR, "fts", "memory.db");
const SERVER_VERSION = "4.0.0";

// ── Helpers ──

function readJSON(relPath) {
  const full = join(MEMORY_DIR, relPath);
  if (!existsSync(full)) return null;
  try { return JSON.parse(readFileSync(full, "utf-8")); }
  catch { return null; }
}

function writeJSON(relPath, data) {
  const full = join(MEMORY_DIR, relPath);
  const dir = full.substring(0, full.lastIndexOf(sep));
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  writeFileSync(full, JSON.stringify(data, null, 2), "utf-8");
  return full;
}

function listJSONFiles(dir) {
  const abs = join(MEMORY_DIR, dir);
  if (!existsSync(abs)) return [];
  return readdirSync(abs).filter((f) => f.endsWith(".json")).sort();
}

function now() { return new Date().toISOString(); }

function genId() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `mem-${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

/**
 * v2: 生成 fingerprint 用于查重
 * 算法: sorted(tags).join(',') + '|' + summary.trim().slice(0,50).toLowerCase()
 */
function calcFingerprint(tags, summary) {
  const sorted = (tags || []).sort().join(",");
  const head = (summary || "").trim().slice(0, 50).toLowerCase();
  return `${sorted}|${head}`;
}

/**
 * v2: 计算 recency_factor
 */
function recencyFactor(lastHit) {
  if (!lastHit) return 1.0;
  const diffDays = (Date.now() - new Date(lastHit).getTime()) / 86400000;
  if (diffDays <= 1) return 3.0;
  if (diffDays <= 7) return 1.5;
  if (diffDays <= 30) return 1.0;
  return 0.5;
}

/**
 * v2: 计算 score
 */
function calcScore(hitCount, lastHit) {
  return Math.round((hitCount || 1) * recencyFactor(lastHit) * 10) / 10;
}

/**
 * v2: 按 fingerprint 在所有条目中搜索匹配
 */
function searchByFingerprint(fp) {
  // 🥇 Priority 1: Check consolidated cache first
  let result = null;
  const consolidated = readJSON("curated/consolidated.json");
  if (consolidated && consolidated.entries) {
    for (const e of consolidated.entries) {
      const efp = e.fingerprint || calcFingerprint(e.tags, e.summary);
      if (efp === fp && e.tier !== "archive") return e;
    }
  }
  // 🥈 Priority 1.5: Raw logs (full detail fallback if title_only found above)
  if (!result) {
    const rawFiles = listJSONFiles("auto/raw");
    for (const file of rawFiles) {
      const entries = readJSON(`auto/raw/${file}`) || [];
      for (const e of entries) {
        const efp = e.fp || calcFingerprint([], e.s || '');
        if (efp === fp) return { _raw_source: `auto/raw/${file}`, summary: e.s, type: e.tp, fingerprint: fp };
      }
    }
  }
  // 🥈 Priority 2: Fall back to auto/ daily files
  const autoFiles = listJSONFiles("auto");
  for (const file of autoFiles) {
    const entries = readJSON(`auto/${file}`) || [];
    for (const e of entries) {
      const efp = e.fingerprint || calcFingerprint(e.tags, e.summary);
      if (efp === fp && e.tier !== "archive") return e;
    }
  }
  // 🥉 Priority 3: Other curated files
  const curatedFiles = listJSONFiles("curated");
  for (const file of curatedFiles) {
    if (file === "consolidated.json") continue;  // already checked
    const entry = readJSON(`curated/${file}`);
    if (!entry) continue;
    const arr = Array.isArray(entry) ? entry : [entry];
    for (const e of arr) {
      const efp = e.fingerprint || calcFingerprint(e.tags, e.summary);
      if (efp === fp && e.tier !== "archive") return e;
    }
  }
  return null;
}

/**
 * v2: 收集所有非 archive 条目（用于搜索）
 */
function collectAllEntries() {

/**
 * v4: FTS5 full-text search via SQLite
 * Returns entries sorted by BM25 relevance, or null on error.
 */
function ftsSearch(query, typeFilter, tierFilter, limit) {
  try {
    // existsSync already imported at top
    if (!existsSync(FTS_DB)) return null;
    const db = new Database(FTS_DB, { readonly: true });
    let sql = `SELECT m.id, m.type, m.summary, m.detail, m.tags, m.score, m.tier, m.hit_count,
                      m.timestamp, m.author, fts.rank
               FROM memories_fts fts
               JOIN memories m ON m.rowid = fts.rowid
               WHERE memories_fts MATCH ?`;
    const params = [query];
    if (typeFilter) { sql += ` AND m.type = ?`; params.push(typeFilter); }
    if (tierFilter) { sql += ` AND m.tier = ?`; params.push(tierFilter); }
    sql += ` ORDER BY fts.rank LIMIT ?`;
    params.push(limit || 10);
    const rows = db.prepare(sql).all(...params);
    db.close();
    return rows.map(r => ({
      id: r.id, type: r.type, summary: r.summary, detail: r.detail,
      tags: r.tags ? r.tags.split(",") : [],
      score: r.score, tier: r.tier, hit_count: r.hit_count,
      timestamp: r.timestamp, author: r.author,
      fts_rank: r.rank
    }));
  } catch(e) {
    console.error("[SMS-v4] FTS search error:", e.message);
    return null;
  }
}
  const results = [];
  const seen = new Set();  // dedup by id

  function addEntry(e) {
    if (e && e.id && !seen.has(e.id) && e.tier !== "archive") {
      e.score = calcScore(e.hit_count, e.last_hit);
      seen.add(e.id);
      results.push(e);
    }
  }

  // 🥇 Priority 1: Consolidated cache (highest priority)
  const consolidated = readJSON("curated/consolidated.json");
  if (consolidated && consolidated.entries) {
    for (const e of consolidated.entries) addEntry(e);
  }

  // 🥈 Priority 2: Individual auto/ daily files (fallback)
  const autoFiles = listJSONFiles("auto");
  for (const file of autoFiles) {
    const entries = readJSON(`auto/${file}`) || [];
    for (const e of entries) addEntry(e);
  }

  // 🥉 Priority 3: Other curated files
  const curatedFiles = listJSONFiles("curated");
  for (const file of curatedFiles) {
    if (file === "consolidated.json") continue;
    const entry = readJSON(`curated/${file}`);
    if (!entry) continue;
    const arr = Array.isArray(entry) ? entry : [entry];
    for (const e of arr) addEntry(e);
  }

  return results;
}

// ── MCP Server ──

const server = new Server(
  { name: SERVER_NAME, version: SERVER_VERSION },
  { capabilities: { resources: {}, tools: {} } }
);

// ── Resources ──

server.setRequestHandler(ListResourcesRequestSchema, async () => {
  const resources = [
    { uri: "ems://index", name: "Memory Index (JSON)", description: "Master index", mimeType: "application/json" },
    { uri: "ems://cache", name: "Memory Cache", description: "Hot tier + score summary", mimeType: "application/json" },
    { uri: "ems://schema", name: "Memory Schema v2", description: "EMS v2 schema with fingerprint, score, tier", mimeType: "application/json" },
    { uri: "ems://skill", name: "Memory Skill (EMS v2)", description: "EMS v2 behavior guidelines", mimeType: "text/markdown" },
    { uri: "ems://hot", name: "Hot Tier Entries", description: "Top 20 scored entries auto-loaded in sessions", mimeType: "application/json" },
    { uri: "ems://consolidated", name: "Consolidated Memory (Prioritized)", description: "🥇 最高优先级记忆 —— 所有去重合并后按score排序的条目", mimeType: "application/json" },
    { uri: "ems://stats", name: "Memory Stats", description: "Tier distribution, total entries, score range", mimeType: "application/json" },
  ];

  const autoFiles = listJSONFiles("auto");
  for (const f of autoFiles.slice(-7)) {
    const name = f.replace(".json","");
    resources.push({ uri: `ems://auto/${name}`, name: `Auto entries: ${name}`, mimeType: "application/json" });
  }

  return { resources };
});

server.setRequestHandler(ListResourceTemplatesRequestSchema, async () => ({
  resourceTemplates: [
    { uriTemplate: "ems://auto/{date}", name: "Auto entries by date", mimeType: "application/json" },
    { uriTemplate: "ems://curated/{id}", name: "Curated entry by id", mimeType: "application/json" },
  ],
}));

server.setRequestHandler(ReadResourceRequestSchema, async (req) => {
  const uri = req.params.uri;
  const send = (data, mime = "application/json") => ({ contents: [{ uri, mimeType: mime, text: JSON.stringify(data, null, 2) }] });

  if (uri === "ems://index") return send(readJSON("index.json") || {});
  if (uri === "ems://cache") return send(readJSON("cache/memory_cache.json") || {});
  if (uri === "ems://schema") return send(readJSON("schema.json") || {});
  if (uri === "ems://skill") {
    const p = join(MEMORY_DIR, "MEMORY_SKILL.md");
    return { contents: [{ uri, mimeType: "text/markdown", text: existsSync(p) ? readFileSync(p, "utf-8") : "# not found" }] };
  }

  // Hot tier
  if (uri === "ems://hot") {
    const all = collectAllEntries();
    const hot = all.filter(e => e.tier === "hot" || e.score >= 8).sort((a, b) => b.score - a.score).slice(0, 20);
    return send({ count: hot.length, max: 20, entries: hot.map(e => ({ id: e.id, type: e.type, summary: e.summary, score: e.score, hit_count: e.hit_count, tags: e.tags })) });
  }

  // Consolidated (priority 1)
  if (uri === "ems://consolidated") {
    const data = readJSON("curated/consolidated.json");
    return { contents: [{ uri, mimeType: "application/json", text: JSON.stringify(data ?? { entries: [] }, null, 2) }] };
  }

  // Stats
  if (uri === "ems://stats") {
    const all = collectAllEntries();
    const hot = all.filter(e => e.tier === "hot" || e.score >= 8).length;
    const warm = all.filter(e => e.tier === "warm" || (e.score >= 3 && e.score < 8)).length;
    const cold = all.filter(e => e.tier === "cold" || e.score < 3).length;
    return send({ total: all.length, hot: Math.min(hot, 20), warm: Math.min(warm, 100), cold, archive_entries_skipped: 0 });
  }

  const autoMatch = uri.match(/^ems:\/\/auto\/(.+)$/);
  if (autoMatch) return send(readJSON(`auto/${autoMatch[1]}.json`) || []);

  const curatedMatch = uri.match(/^ems:\/\/curated\/(.+)$/);
  if (curatedMatch) {
    const d = readJSON(`curated/${curatedMatch[1]}.json`);
    return send(d || {});
  }

  throw new Error(`Resource not found: ${uri}`);
});

// ── Tools ──

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
    
      name: "search_fts",
      description: "v4: FTS5 全文搜索引擎 — 支持模糊匹配、中英文混搜、BM25 相关性排序。比 search_memories 更灵活，忘记关键词也能搜到。",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "要搜索的内容（支持不完整关键词）" },
          type: { type: "string", description: "Filter by type" },
          tier: { type: "string", enum: ["hot", "warm", "cold"] },
          limit: { type: "number", minimum: 1, maximum: 50 },
        },
        required: [],
      },
    },
    {
      name: "search_memories",
      description: "v2: 按 query / type / tier / tags 搜索记忆，按 score 排序",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search keyword" },
          type: { type: "string", description: "Filter by type" },
          tier: { type: "string", enum: ["hot", "warm", "cold"] },
          tags: { type: "array", items: { type: "string" }, description: "Filter by tags" },
          days_back: { type: "number", minimum: 1, maximum: 365 },
          limit: { type: "number", minimum: 1, maximum: 50 },
        },
      },
    },
    {
      name: "write_or_merge",
      description: "v2: 写入前查重（fingerprint）。命中则合并(hit_count+1)，不命中则新建。推荐使用这个。",
      inputSchema: {
        type: "object",
        properties: {
          type: { type: "string", enum: ["decision", "knowledge", "preference", "event", "context_switch", "insight"] },
          summary: { type: "string", description: "One-line summary (max 200 chars)", maxLength: 200 },
          detail: { type: "string", description: "Detailed explanation" },
          tags: { type: "array", items: { type: "string" }, description: "Tags for dedup & categorization" },
          importance: { type: "number", minimum: 1, maximum: 5 },
          context: { type: "string" },
          force_new: { type: "boolean", description: "跳过查重，强制新建（慎用）" },
          author: { type: "string", description: "Who wrote this (for cross-user merge tracking)" },
        },
        required: ["type", "summary"],
      },
    },
    {
      name: "hit_memory",
      description: "v2: 按 id 标记一条记忆被命中。增加 hit_count，更新 last_hit，重算 score",
      inputSchema: {
        type: "object",
        properties: {
          id: { type: "string", description: "Entry id to mark as hit" },
        },
        required: ["id"],
      },
    },
    {
      name: "get_context",
      description: "获取当前上下文（Hot 层 + 最近 warm 摘要）",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "get_stats",
      description: "v2: 获取记忆系统统计：tier 分布、最高分条目、总条目数",
      inputSchema: { type: "object", properties: {} },
    },
  ],
}));

// ── Tool Handlers ──

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;

  switch (name) {
    // ── search_memories ──
    case "search_fts": {
      const ftsQuery = args?.query || "";
      if (!ftsQuery) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "query required" }) }] };
      }
      const ftsType = args?.type || "";
      const ftsTier = args?.tier || "";
      const ftsLimit = args?.limit || 10;
      
      try {
        const db = new Database(FTS_DB, { readonly: true });
        
        // Try FTS5 full-text search first (works great for English)
        let sql = "SELECT m.id, m.type, m.summary, m.detail, m.tags, m.score, m.tier, m.hit_count, m.timestamp, fts.rank FROM memories_fts fts JOIN memories m ON m.rowid = fts.rowid WHERE memories_fts MATCH ?";
        const params = [ftsQuery];
        if (ftsType) { sql += " AND m.type = ?"; params.push(ftsType); }
        if (ftsTier) { sql += " AND m.tier = ?"; params.push(ftsTier); }
        sql += " ORDER BY fts.rank LIMIT ?";
        params.push(ftsLimit);
        
        const rows = db.prepare(sql).all(...params);
        
        // Update hit_count for found entries
        for (const row of rows) {
          try {
            db.exec("UPDATE memories SET hit_count = hit_count + 1, last_hit = datetime('now') WHERE id = '" + row.id.replace(/'/g, "''") + "'");
          } catch(e) { /* silently continue */ }
        }
        
        if (rows.length > 0) {
          const results = rows.map(r => ({
            id: r.id, type: r.type, summary: r.summary, detail: (r.detail || "").slice(0, 300),
            tags: r.tags ? r.tags.split(",").filter(Boolean) : [],
            score: r.score, tier: r.tier, hit_count: r.hit_count + 1, timestamp: r.timestamp,
            relevance: Math.abs(r.rank)
          }));
          db.close();
          return { content: [{ type: "text", text: JSON.stringify({ total: results.length, query: ftsQuery, entries: results }, null, 2) }] };
        }
        
        // FTS5 returned 0 results - try LIKE fallback (works for CJK)
        const cleanQ = ftsQuery.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, "").trim();
        if (cleanQ) {
          const likeQ = "%" + cleanQ + "%";
          const likeRows = db.prepare("SELECT id, type, summary, detail, tags, score, tier, hit_count, timestamp FROM memories WHERE summary LIKE ? OR detail LIKE ? OR tags LIKE ? LIMIT ?").all(likeQ, likeQ, likeQ, ftsLimit);
          const likeResults = likeRows.map(r => ({
            id: r.id, type: r.type, summary: r.summary, detail: (r.detail || "").slice(0, 300),
            tags: r.tags ? r.tags.split(",").filter(Boolean) : [],
            score: r.score, tier: r.tier, hit_count: r.hit_count, timestamp: r.timestamp,
            relevance: 1.0
          }));
          db.close();
          if (likeResults.length > 0) {
            return { content: [{ type: "text", text: JSON.stringify({ total: likeResults.length, query: ftsQuery, entries: likeResults, mode: "like_fallback" }, null, 2) }] };
          }
        }
        
        db.close();
        return { content: [{ type: "text", text: JSON.stringify({ total: 0, query: ftsQuery, entries: [] }, null, 2) }] };
      } catch (e) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "Search failed: " + e.message, query: ftsQuery }, null, 2) }] };
      }
    }

    case "search_memories": {
      const query = (args?.query || "").toLowerCase();
      const typeFilter = args?.type || "";
      const tierFilter = args?.tier || "";
      const tagFilter = args?.tags || [];
      const daysBack = args?.days_back || 365;
      const limit = args?.limit || 10;
      const cutoff = Date.now() - daysBack * 86400000;

      const all = collectAllEntries();
      const results = [];

      for (const e of all) {
        const ts = new Date(e.timestamp || e.last_hit || Date.now()).getTime();
        if (ts < cutoff) continue;
        if (typeFilter && e.type !== typeFilter) continue;
        if (tierFilter && e.tier !== tierFilter) continue;
        if (query) {
          const haystack = [e.summary, e.detail, ...(e.tags || [])].join(" ").toLowerCase();
          if (!haystack.includes(query)) continue;
        }
        if (tagFilter.length) {
          const etags = new Set(e.tags || []);
          if (!tagFilter.every(t => etags.has(t))) continue;
        }
        // On search hit, increment hit_count (in-memory for now)
        e.hit_count = (e.hit_count || 1) + 1;
        e.last_hit = now();
        e.score = calcScore(e.hit_count, e.last_hit);
        results.push({
          id: e.id,
          type: e.type,
          summary: e.summary,
          tier: e.tier,
          score: e.score,
          hit_count: e.hit_count,
          last_hit: e.last_hit,
          tags: e.tags || [],
          importance: e.importance,
        });
      }

      // Sort by score descending
      results.sort((a, b) => b.score - a.score);
      const sliced = results.slice(0, limit);

      return {
        content: [{ type: "text", text: JSON.stringify({
          total_hits: sliced.length, query, limit,
          entries: sliced,
        }, null, 2) }],
      };
    }

    // ── write_or_merge ──
    case "write_or_merge": {
      const type = args?.type || "knowledge";
      const summary = (args?.summary || "").trim();
      const detail = (args?.detail || "").trim();
      const tags = args?.tags || [];
      const importance = args?.importance || 3;
      const context = args?.context || "";
      const forceNew = args?.force_new || false;

      if (!summary) {
        return { content: [{ type: "text", text: "Error: summary required." }] };
      }

      // 1. Generate fingerprint
      const fp = calcFingerprint(tags, summary);

      // 2. Search existing (unless force_new)
      if (!forceNew) {
        const existing = searchByFingerprint(fp);
        if (existing) {
          // Merge: update fields, increment hit_count
          existing.hit_count = (existing.hit_count || 1) + 1;
          // Merge contributors
          const existingContribs = new Set(existing.contributors || [existing.author || "unknown"]);
          const newAuthor = args?.author || process.env.EMS_AUTHOR || "unknown";
          existing.contributors = [...existingContribs, newAuthor].filter((v,i,a) => a.indexOf(v)===i);
          existing.last_author = newAuthor;
          existing.author = existing.author || newAuthor;
          existing.last_hit = now();
          existing.detail = existing.detail || detail;
          if (detail && !existing.detail.includes(detail)) {
            existing.detail += "\n---\n" + detail;
          }
          existing.score = calcScore(existing.hit_count, existing.last_hit);
          if (importance > (existing.importance || 1)) existing.importance = importance;

          // Write back
          const todayFile = `auto/${existing.timestamp?.slice(0, 10) || new Date().toISOString().slice(0, 10)}.json`;
          const entries = readJSON(todayFile) || [];
          const idx = entries.findIndex(e => e.id === existing.id);
          if (idx >= 0) {
            entries[idx] = existing;
            writeJSON(todayFile, entries);
          }

          return {
            content: [{ type: "text", text: JSON.stringify({
              status: "merged", id: existing.id, action: "merged",
              hit_count: existing.hit_count, score: existing.score,
              fingerprint: fp,
            }, null, 2) }],
          };
        }
      }

      // 3. New entry
      const newEntry = {
        author: args?.author || process.env.EMS_AUTHOR || "unknown",
        contributors: [args?.author || process.env.EMS_AUTHOR || "unknown"],
        git_origin: process.env.EMS_GIT_REPO || "",
        last_author: args?.author || process.env.EMS_AUTHOR || "unknown",
        id: genId(),
        timestamp: now(),
        type,
        summary,
        detail,
        tags,
        fingerprint: fp,
        hit_count: 1,
        last_hit: now(),
        score: calcScore(1, now()),
        tier: "hot",
        importance,
        context,
        related_ids: [],
      };

      const today = new Date().toISOString().slice(0, 10);
      const relPath = `auto/${today}.json`;
      const existingEntries = readJSON(relPath) || [];
      existingEntries.push(newEntry);
      writeJSON(relPath, existingEntries);

      return {
        content: [{ type: "text", text: JSON.stringify({
          status: "created", id: newEntry.id, action: "new",
          fingerprint: fp, path: relPath,
        }, null, 2) }],
      };
    }

    // ── hit_memory ──
    case "hit_memory": {
      const hitId = args?.id || "";
      if (!hitId) return { content: [{ type: "text", text: "Error: id required." }] };

      const autoFiles = listJSONFiles("auto");
      let found = false;
      for (const file of autoFiles) {
        const entries = readJSON(`auto/${file}`) || [];
        const idx = entries.findIndex(e => e.id === hitId);
        if (idx >= 0) {
          entries[idx].hit_count = (entries[idx].hit_count || 1) + 1;
          entries[idx].last_hit = now();
          entries[idx].score = calcScore(entries[idx].hit_count, entries[idx].last_hit);
          writeJSON(`auto/${file}`, entries);
          found = true;
          break;
        }
      }

      if (!found) {
        return { content: [{ type: "text", text: JSON.stringify({ status: "not_found", id: hitId }) }] };
      }

      return { content: [{ type: "text", text: JSON.stringify({ status: "ok", id: hitId, action: "hit_count++" }) }] };
    }

    // ── get_context ──
    case "get_context": {
      const cache = readJSON("cache/memory_cache.json") || {};
      const all = collectAllEntries();
      const hot = all.filter(e => e.tier === "hot" || e.score >= 8).sort((a, b) => b.score - a.score).slice(0, 20);

      return {
        content: [{ type: "text", text: JSON.stringify({
          cache_summary: {
            hot_count: cache.hot_tier?.count || 0,
            warm_count: cache.warm_tier?.count || 0,
            cold_count: cache.cold_tier?.count || 0,
          },
          hot_tier: hot.map(e => ({
            id: e.id, type: e.type, summary: e.summary,
            score: e.score, hit_count: e.hit_count, tags: e.tags,
          })),
        }, null, 2) }],
      };
    }

    // ── get_stats ──
    case "get_stats": {
      const all = collectAllEntries();
      const hot = all.filter(e => e.tier === "hot" || e.score >= 8);
      const warm = all.filter(e => e.tier === "warm" || (e.score >= 3 && e.score < 8));
      const cold = all.filter(e => !e.tier || e.tier === "cold" || e.score < 3);
      const top5 = all.sort((a, b) => b.score - a.score).slice(0, 5);

      return {
        content: [{ type: "text", text: JSON.stringify({
          total: all.length,
          hot: { count: Math.min(hot.length, 20), max: 20 },
          warm: { count: Math.min(warm.length, 100), max: 100 },
          cold: { count: cold.length },
          top_scored: top5.map(e => ({ id: e.id, summary: e.summary, score: e.score, hit_count: e.hit_count, tier: e.tier })),
          schema_version: "2.0",
        }, null, 2) }],
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

// ── Start ──

async function main() {
  console.error(`[EMS-v2] Starting server`);
  console.error(`[EMS-v2] MEMORY_DIR = ${MEMORY_DIR}`);
  console.error(`[EMS-v2] Exists: ${existsSync(MEMORY_DIR)}`);

  if (!existsSync(MEMORY_DIR)) {
    console.error(`[EMS-v2] ⚠️  Memory directory not found`);
  }

  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`[EMS-v2] Server ready ✓`);
}

main().catch((err) => {
  console.error(`[EMS-v2] Fatal:`, err);
  process.exit(1);
});

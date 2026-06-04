#!/usr/bin/env node
/**
 * SMS MCP Server — Smart Memory System × Claude Code Bridge
 *
 * Exposes SMS structured memory as MCP resources + tools,
 * so Claude Code (or any MCP client) can read and write memory.
 *
 * Usage:
 *   node server.js --dir /path/to/memory
 *   node server.js   (uses SMS_MEMORY_DIR env or ./memory)
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

// ── Config ──────────────────────────────────────────────────────

const args = process.argv.slice(2);
const dirIdx = args.indexOf("--dir");
const MEMORY_DIR = resolve(
  dirIdx !== -1 && args[dirIdx + 1]
    ? args[dirIdx + 1]
    : process.env.SMS_MEMORY_DIR
      ? process.env.SMS_MEMORY_DIR
      : join(process.cwd(), "memory")
);

const SERVER_NAME = "sms-mcp";
const SERVER_VERSION = "1.0.0";

// ── Helpers ─────────────────────────────────────────────────────

function readJSON(relPath) {
  const full = join(MEMORY_DIR, relPath);
  if (!existsSync(full)) return null;
  try {
    return JSON.parse(readFileSync(full, "utf-8"));
  } catch {
    return null;
  }
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
  return readdirSync(abs)
    .filter((f) => f.endsWith(".json"))
    .sort();
}

function now() {
  return new Date().toISOString();
}

function genId() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `mem-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

// ── MCP Server ──────────────────────────────────────────────────

const server = new Server(
  { name: SERVER_NAME, version: SERVER_VERSION },
  { capabilities: { resources: {}, tools: {} } }
);

// ── Resources ─────────────────────────────────────────────────

server.setRequestHandler(ListResourcesRequestSchema, async () => {
  const resources = [
    {
      uri: "sms://index",
      name: "Memory Index (JSON)",
      description: "Master index of all memory entries",
      mimeType: "application/json",
    },
    {
      uri: "sms://cache",
      name: "Memory Cache",
      description: "Pre-loaded context for session start",
      mimeType: "application/json",
    },
    {
      uri: "sms://schema",
      name: "Memory Schema",
      description: "SMS data schema and quality rules",
      mimeType: "application/json",
    },
    {
      uri: "sms://skill",
      name: "Memory Skill (SMS behavior guidelines)",
      description: "How SMS decides what to capture",
      mimeType: "text/markdown",
    },
  ];

  // Add all auto entry files
  const autoFiles = listJSONFiles("auto");
  for (const f of autoFiles) {
    const name = f.replace(".json", "");
    resources.push({
      uri: `sms://auto/${name}`,
      name: `Auto entries: ${name}`,
      description: `Auto-captured memory entries for ${name}`,
      mimeType: "application/json",
    });
  }

  // Add all curated files
  const curatedFiles = listJSONFiles("curated");
  for (const f of curatedFiles) {
    resources.push({
      uri: `sms://curated/${f.replace(".json", "")}`,
      name: `Curated: ${f}`,
      description: "Long-term consolidated memory entry",
      mimeType: "application/json",
    });
  }

  return { resources };
});

server.setRequestHandler(ListResourceTemplatesRequestSchema, async () => ({
  resourceTemplates: [
    {
      uriTemplate: "sms://auto/{date}",
      name: "Auto memory entries by date",
      description: "SMS auto entries for a specific date (YYYY-MM-DD)",
      mimeType: "application/json",
    },
    {
      uriTemplate: "sms://curated/{id}",
      name: "Curated memory entry",
      description: "Long-term curated memory entry by name",
      mimeType: "application/json",
    },
  ],
}));

server.setRequestHandler(ReadResourceRequestSchema, async (req) => {
  const uri = req.params.uri;

  if (uri === "sms://index") {
    const data = readJSON("index.json");
    return { contents: [{ uri, mimeType: "application/json", text: JSON.stringify(data ?? {}, null, 2) }] };
  }
  if (uri === "sms://cache") {
    const data = readJSON("cache/memory_cache.json");
    return { contents: [{ uri, mimeType: "application/json", text: JSON.stringify(data ?? {}, null, 2) }] };
  }
  if (uri === "sms://schema") {
    const data = readJSON("schema.json");
    return { contents: [{ uri, mimeType: "application/json", text: JSON.stringify(data ?? {}, null, 2) }] };
  }
  if (uri === "sms://skill") {
    const filePath = join(MEMORY_DIR, "MEMORY_SKILL.md");
    const text = existsSync(filePath) ? readFileSync(filePath, "utf-8") : "# MEMORY_SKILL.md not found";
    return { contents: [{ uri, mimeType: "text/markdown", text }] };
  }

  // sms://auto/YYYY-MM-DD
  const autoMatch = uri.match(/^ems:\/\/auto\/(.+)$/);
  if (autoMatch) {
    const data = readJSON(`auto/${autoMatch[1]}.json`);
    return { contents: [{ uri, mimeType: "application/json", text: JSON.stringify(data ?? [], null, 2) }] };
  }

  // sms://curated/xxx
  const curatedMatch = uri.match(/^ems:\/\/curated\/(.+)$/);
  if (curatedMatch) {
    const data = readJSON(`curated/${curatedMatch[1]}.json`);
    return { contents: [{ uri, mimeType: "application/json", text: JSON.stringify(data ?? {}, null, 2) }] };
  }

  throw new Error(`Resource not found: ${uri}`);
});

// ── Tools ────────────────────────────────────────────────────

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "search_memories",
      description: "Search SMS memory by query, type, or date range",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search keyword in summary/detail/tags" },
          type: { type: "string", description: "Filter by entry type: decision | knowledge | preference | event | context_switch | insight" },
          days_back: { type: "number", description: "How many days back to search (default: 30)", minimum: 1, maximum: 365 },
          limit: { type: "number", description: "Max results (default: 10)", minimum: 1, maximum: 50 },
        },
        required: [],
      },
    },
    {
      name: "write_memory",
      description: "Write a new auto memory entry to SMS",
      inputSchema: {
        type: "object",
        properties: {
          type: {
            type: "string",
            description: "Entry type",
            enum: ["decision", "knowledge", "preference", "event", "context_switch", "insight"],
          },
          summary: { type: "string", description: "One-line summary (max 200 chars)", maxLength: 200 },
          detail: { type: "string", description: "Detailed explanation" },
          tags: {
            type: "array",
            items: { type: "string" },
            description: "Tags for categorization",
          },
          importance: {
            type: "number",
            description: "1-5 (1=trivial, 5=critical)",
            minimum: 1,
            maximum: 5,
          },
          context: { type: "string", description: "Session or project context" },
        },
        required: ["type", "summary"],
      },
    },
    {
      name: "get_context",
      description: "Get current SMS context cache (latest summaries for session start)",
      inputSchema: {
        type: "object",
        properties: {},
        required: [],
      },
    },
    {
      name: "get_recent",
      description: "Get the most recent memory entries",
      inputSchema: {
        type: "object",
        properties: {
          limit: { type: "number", description: "Max entries (default: 10)", minimum: 1, maximum: 50 },
        },
        required: [],
      },
    },
    {
      name: "list_types",
      description: "List available memory types with descriptions",
      inputSchema: {
        type: "object",
        properties: {},
        required: [],
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;

  switch (name) {
    case "search_memories": {
      const query = (args?.query || "").toLowerCase();
      const typeFilter = args?.type || "";
      const daysBack = args?.days_back || 30;
      const limit = args?.limit || 10;

      const cutoff = Date.now() - daysBack * 86400000;
      const results = [];

      const autoFiles = listJSONFiles("auto");
      for (const file of autoFiles) {
        const entries = readJSON(`auto/${file}`) || [];
        for (const e of entries) {
          const ts = new Date(e.timestamp).getTime();
          if (ts < cutoff) continue;
          if (typeFilter && e.type !== typeFilter) continue;
          if (query) {
            const haystack = [e.summary, e.detail, ...(e.tags || [])].join(" ").toLowerCase();
            if (!haystack.includes(query)) continue;
          }
          results.push(e);
        }
      }

      // Also search curated
      const curatedFiles = listJSONFiles("curated");
      for (const file of curatedFiles) {
        const entries = readJSON(`curated/${file}`);
        if (!entries) continue;
        const arr = Array.isArray(entries) ? entries : [entries];
        for (const e of arr) {
          if (!e.timestamp) continue;
          const ts = new Date(e.timestamp).getTime();
          if (ts < cutoff) continue;
          if (typeFilter && e.type !== typeFilter) continue;
          if (query) {
            const haystack = [e.summary, e.detail, ...(e.tags || [])].join(" ").toLowerCase();
            if (!haystack.includes(query)) continue;
          }
          results.push(e);
        }
      }

      results.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
      const sliced = results.slice(0, limit);

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                total: sliced.length,
                query,
                type_filter: typeFilter || "any",
                days_back: daysBack,
                entries: sliced.map((e) => ({
                  id: e.id,
                  timestamp: e.timestamp,
                  type: e.type,
                  summary: e.summary,
                  tags: e.tags || [],
                  importance: e.importance,
                })),
              },
              null,
              2
            ),
          },
        ],
      };
    }

    case "write_memory": {
      const type = args?.type || "knowledge";
      const summary = args?.summary || "";
      const detail = args?.detail || "";
      const tags = args?.tags || [];
      const importance = args?.importance || 3;
      const context = args?.context || "";

      if (!summary) {
        return { content: [{ type: "text", text: "Error: summary is required." }] };
      }

      const entry = {
        id: genId(),
        timestamp: now(),
        type,
        summary,
        detail,
        tags,
        importance,
        context,
        related_ids: [],
      };

      // Write to today's auto file
      const today = new Date().toISOString().slice(0, 10);
      const relPath = `auto/${today}.json`;
      const existing = readJSON(relPath) || [];
      existing.push(entry);
      writeJSON(relPath, existing);

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({ status: "ok", id: entry.id, path: relPath, entry }, null, 2),
          },
        ],
      };
    }

    case "get_context": {
      const cache = readJSON("cache/memory_cache.json") || {};
      const autoFiles = listJSONFiles("auto");
      const recent = [];

      for (const file of autoFiles.slice(-3).reverse()) {
        const entries = readJSON(`auto/${file}`) || [];
        recent.push(...entries.slice(-5));
      }
      recent.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                cache,
                recent_entries_count: recent.length,
                recent_entries: recent.slice(0, 10).map((e) => ({
                  id: e.id,
                  timestamp: e.timestamp,
                  type: e.type,
                  summary: e.summary,
                  importance: e.importance,
                })),
              },
              null,
              2
            ),
          },
        ],
      };
    }

    case "get_recent": {
      const limit = args?.limit || 10;
      const results = [];

      const autoFiles = listJSONFiles("auto");
      for (const file of autoFiles.slice(-5).reverse()) {
        const entries = readJSON(`auto/${file}`) || [];
        results.push(...entries);
      }

      results.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(results.slice(0, limit), null, 2),
          },
        ],
      };
    }

    case "list_types": {
      const schema = readJSON("schema.json");
      const types = schema?.entry_types || {};
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(types, null, 2),
          },
        ],
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

// ── Start ────────────────────────────────────────────────────

async function main() {
  console.error(`[SMS-MCP] Starting server`);
  console.error(`[SMS-MCP] MEMORY_DIR = ${MEMORY_DIR}`);
  console.error(`[SMS-MCP] Exists: ${existsSync(MEMORY_DIR)}`);

  if (!existsSync(MEMORY_DIR)) {
    console.error(`[SMS-MCP] ⚠️  Memory directory does not exist yet`);
    console.error(`[SMS-MCP] Create it or point --dir to an existing SMS store`);
  }

  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`[SMS-MCP] Server ready ✓`);
}

main().catch((err) => {
  console.error(`[SMS-MCP] Fatal error:`, err);
  process.exit(1);
});

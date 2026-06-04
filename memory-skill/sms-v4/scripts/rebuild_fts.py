#!/usr/bin/env python3
"""
EMS v4 — FTS5 Search Index Builder
从 consolidated.json + auto/*.json 构建 SQLite FTS5 全文索引。
JSON 是主数据源，SQLite 只做搜索加速。
"""
import json, os, sys, sqlite3, glob, re

# CJK-ASCII boundary space inserter (for FTS5 tokenization)
# Ensures ASCII keywords adjacent to Chinese chars get separate tokens
def add_boundary_spaces(text):
    text = re.sub(r'([\u4e00-\u9fff])([a-zA-Z0-9])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z0-9])([\u4e00-\u9fff])', r'\1 \2', text)
    return re.sub(r' +', ' ', text)

MEMORY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AUTO_DIR = os.path.join(MEMORY_DIR, 'auto')
CURATED_FILE = os.path.join(MEMORY_DIR, 'curated', 'consolidated.json')
FTS_DB = os.path.join(MEMORY_DIR, 'fts', 'memory.db')

def log(msg): print(f"[SMS-v4] {msg}")

def rebuild():
    os.makedirs(os.path.dirname(FTS_DB), exist_ok=True)
    conn = sqlite3.connect(FTS_DB)
    c = conn.cursor()

    # Main memory table
    c.execute('DROP TABLE IF EXISTS memories')
    c.execute('''
        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            type TEXT,
            summary TEXT,
            detail TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            fingerprint TEXT DEFAULT '',
            hit_count INTEGER DEFAULT 1,
            score REAL DEFAULT 0,
            tier TEXT DEFAULT 'warm',
            importance INTEGER DEFAULT 3,
            author TEXT DEFAULT '',
            contributors TEXT DEFAULT '',
            date TEXT
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_type ON memories(type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tier ON memories(tier)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_date ON memories(date)')

    # FTS5 with INTERNAL content (most reliable)
    c.execute('DROP TABLE IF EXISTS memories_fts')
    c.execute('''
        CREATE VIRTUAL TABLE memories_fts USING fts5(
            summary, detail, tags, fingerprint,
            tokenize='ascii'
        )
    ''')

    # Collect all entries (dedup by id)
    all_entries = []
    seen = set()

    if os.path.exists(CURATED_FILE):
        with open(CURATED_FILE) as f:
            data = json.load(f)
        for e in data.get('entries', []):
            eid = e.get('id', '')
            if eid and eid not in seen:
                seen.add(eid)
                all_entries.append(e)

    for fname in sorted(os.listdir(AUTO_DIR)):
        if not fname.endswith('.json') or fname == 'raw':
            continue
        fpath = os.path.join(AUTO_DIR, fname)
        try:
            with open(fpath) as f:
                entries = json.load(f)
        except:
            continue
        for e in entries:
            eid = e.get('id', '')
            if eid and eid not in seen:
                seen.add(eid)
                all_entries.append(e)

    # Insert into memories + FTS5
    count = 0
    for e in all_entries:
        ts = e.get('timestamp', '')
        summary = e.get('summary', '') or ''
        detail = e.get('detail', '') or ''
        tags_str = ','.join(e.get('tags', []) or [])
        fp = e.get('fingerprint', '') or ''
        contribs_str = ','.join(e.get('contributors', []) or [])

        c.execute('''
            INSERT INTO memories
            (id, timestamp, type, summary, detail, tags, fingerprint,
             hit_count, score, tier, importance, author, contributors, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            e.get('id', ''),
            ts,
            e.get('type', 'knowledge'),
            summary,
            detail,
            tags_str,
            fp,
            e.get('hit_count', 1),
            e.get('score', 0),
            e.get('tier', 'warm'),
            e.get('importance', 3),
            e.get('author', ''),
            contribs_str,
            ts[:10] if ts else ''
        ))
        # Populate FTS5 with boundary-spaced text (ensures ASCII keywords adjacent to CJK get separate tokens)
        c.execute('''
            INSERT INTO memories_fts(summary, detail, tags, fingerprint)
            VALUES (?, ?, ?, ?)
        ''', (add_boundary_spaces(summary), add_boundary_spaces(detail), tags_str, add_boundary_spaces(fp)))
        count += 1

    conn.commit()

    # Verify
    c.execute('SELECT COUNT(*) FROM memories_fts')
    fts_count = c.fetchone()[0]
    log(f"Indexed: {count} entries in memories, {fts_count} in FTS5")

    # Test searches
    log("Sample FTS5 searches:")
    for q in ['grep', 'pipe', 'tennis', 'book', 'ssh', 'clone', 'github']:
        try:
            c.execute("SELECT COUNT(*) FROM memories_fts WHERE memories_fts MATCH ?", (q,))
            n = c.fetchone()[0]
            if n:
                c.execute("SELECT summary FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT 1", (q,))
                r = c.fetchone()
                log(f"  ✅ '{q}' → {n} hit(s): {r[0][:50]}")
            else:
                log(f"  ❌ '{q}' → 0 hits")
        except Exception as e:
            log(f"  ⚠️ '{q}' → error: {e}")

    conn.close()
    return count

if __name__ == '__main__':
    log("=== FTS5 Index Build ===")
    rebuild()
    log("Done.")

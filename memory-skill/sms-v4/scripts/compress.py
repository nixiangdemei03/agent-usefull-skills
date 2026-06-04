#!/usr/bin/env python3
"""
EMS v4 — Compress Engine
三层压缩：raw 日志 → 去重合并 → title_only 分级 → consolidated.json
含 dirty check，无变更时跳过（0.001s）。

--auto mode: 用于每分钟 cron。检查最后活动时间和最后压缩时间，
  只有对话停止 >1 分钟且上次压缩 >1 分钟前才执行。
"""
import json, os, sys, glob
from datetime import datetime, timezone
from collections import defaultdict

MEMORY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AUTO_DIR = os.path.join(MEMORY_DIR, 'auto')
RAW_DIR = os.path.join(AUTO_DIR, 'raw')
CURATED_FILE = os.path.join(MEMORY_DIR, 'curated', 'consolidated.json')
CACHE_FILE = os.path.join(MEMORY_DIR, 'cache', 'memory_cache.json')

# Types that always keep full detail
FULL_TYPES = {'knowledge', 'decision', 'insight', 'failure'}
# Types that prefer title_only
TITLE_TYPES = {'event', 'context_switch', 'chat', 'chat_insight', 'preference'}

def log(msg): print(f"[SMS-v4] {msg}")

def latest_mtime(directory, pattern='*.json'):
    """Latest modification time in a directory, or 0 if empty"""
    files = glob.glob(os.path.join(directory, pattern))
    if not files:
        return 0
    return max(os.path.getmtime(f) for f in files)

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def calc_recency(last_hit_str):
    if not last_hit_str:
        return 1.0
    try:
        diff_days = (datetime.now().timestamp() - datetime.fromisoformat(last_hit_str).timestamp()) / 86400
    except:
        return 1.0
    if diff_days <= 1:    return 3.0
    elif diff_days <= 7:  return 1.5
    elif diff_days <= 30: return 1.0
    else:                 return 0.5

def build_fingerprint(e):
    fp = e.get('fingerprint', '') or e.get('fp', '')
    if fp:
        return fp
    tags = sorted(e.get('tags', []) or [])
    s = (e.get('summary', '') or e.get('s', '') or '').strip()[:50].lower()
    return ','.join(tags) + '|' + s

LOCK_FILE = os.path.join(MEMORY_DIR, '.last_compress')

# ─── Auto Mode (for cron / heartbeat) ─────────────────────────
# Called every 60s. Only compresses if:
# 1. New data exists (dirty check)
# 2. Conversation has been stopped >1 minute
# 3. Last compress was >1 minute ago
AUTO_MODE = '--auto' in sys.argv
if AUTO_MODE:
    now_ts = datetime.now().timestamp()

    # Check 1: was last compress < 1 min ago? (avoid racing)
    last_compress = 0
    if os.path.exists(LOCK_FILE):
        last_compress = os.path.getmtime(LOCK_FILE)
    if now_ts - last_compress < 60:
        log("Auto: SKIP (last compress < 1 min ago)")
        sys.exit(0)

    # Check 2: has raw/ dir actually changed since last compress?
    if os.path.exists(CURATED_FILE):
        consolidated_mtime = os.path.getmtime(CURATED_FILE)
        latest_raw = latest_mtime(RAW_DIR)
        latest_auto = latest_mtime(AUTO_DIR)
        if consolidated_mtime >= latest_raw and consolidated_mtime >= latest_auto:
            # Update lock so we don't keep checking
            open(LOCK_FILE, 'w').close()
            log("Auto: SKIP (consolidated already current)")
            sys.exit(0)

    log("Auto: NEED COMPRESS (conversation idle, new data found)")

# ─── Step 0: Dirty Check ─────────────────────────────────────

log("=== Compress Start ===")

if not os.path.isdir(RAW_DIR):
    os.makedirs(RAW_DIR, exist_ok=True)
    log("Created raw/ directory")

if not AUTO_MODE:
    consolidated_mtime = os.path.getmtime(CURATED_FILE) if os.path.exists(CURATED_FILE) else 0
    latest_raw = latest_mtime(RAW_DIR)
    latest_auto = latest_mtime(AUTO_DIR)

    if consolidated_mtime >= latest_raw and consolidated_mtime >= latest_auto:
        log(f"Dirty check: SKIP (consolidated is current)")
        log(f"  consolidated: {datetime.fromtimestamp(consolidated_mtime).strftime('%H:%M:%S')}")
        log(f"  raw/:         {datetime.fromtimestamp(latest_raw).strftime('%H:%M:%S') if latest_raw else 'empty'}")
        sys.exit(0)

    log(f"Dirty check: NEED COMPRESS")
    log(f"  consolidated: {datetime.fromtimestamp(consolidated_mtime).strftime('%H:%M:%S') if consolidated_mtime else 'new'}")
    log(f"  raw/:         {datetime.fromtimestamp(latest_raw).strftime('%H:%M:%S') if latest_raw else 'empty'}")

# ─── Step 1: Collect all entries (raw + daily + existing consolidated) ──

all_entries = []
source_stats = defaultdict(int)

# 1a) From raw logs
for fname in sorted(os.listdir(RAW_DIR)):
    if not fname.endswith('.raw.json'):
        continue
    entries = load_json(os.path.join(RAW_DIR, fname))
    if not entries:
        continue
    for e in entries:
        if isinstance(e, dict):
            # Normalize raw format → full entry format
            raw_date = fname[:10]  # YYYY-MM-DD from filename
            raw_time = e.get('t', '12:00')
            iso_ts = f'{raw_date}T{raw_time}:00+10:00' if 'T' not in raw_time else raw_time
            norm = {
                '_source': f'raw/{fname}',
                'id': e.get('fp', f'raw-{fname}-{len(all_entries)}')[:30],
                'timestamp': iso_ts,
                'type': e.get('tp', 'knowledge'),
                'summary': e.get('s', '(no title)'),
                'fingerprint': e.get('fp', ''),
                'hit_count': e.get('hit_count', 1),
                'last_hit': iso_ts,
                'detail': e.get('detail', ''),
                'tags': e.get('tags', []),
                'tier': e.get('tier', ''),
                'title_only': False,
            }
            all_entries.append(norm)
            source_stats['raw'] += 1

# 1b) From existing auto/ daily files
for fname in sorted(os.listdir(AUTO_DIR)):
    if not fname.endswith('.json') or fname.startswith('.'):
        continue
    entries = load_json(os.path.join(AUTO_DIR, fname))
    if not entries or not isinstance(entries, list):
        continue
    for e in entries:
        if e.get('tier') == 'archive':
            continue
        e['_source'] = f'auto/{fname}'
        all_entries.append(e)
        source_stats['auto'] += 1

# 1c) From existing consolidated (if any)
consolidated = load_json(CURATED_FILE)
if consolidated and consolidated.get('entries'):
    for e in consolidated['entries']:
        if e.get('tier') == 'archive':
            continue
        e['_source'] = e.get('source_raw', 'curated/consolidated.json')
        all_entries.append(e)
        source_stats['consolidated'] += 1

log(f"Collected: raw={source_stats['raw']} auto={source_stats['auto']} consolidated={source_stats['consolidated']} total={len(all_entries)}")

# ─── Step 2: Fingerprint group & merge ──────────────────────

groups = defaultdict(list)
for e in all_entries:
    fp = build_fingerprint(e)
    if fp:
        groups[fp].append(e)

log(f"Fingerprint groups: {len(groups)}")

merged_entries = []
for fp, group in groups.items():
    # Sort by hit_count desc
    group.sort(key=lambda e: (0 if e.get("_source","").startswith("auto") else 1, e.get("hit_count",1)), reverse=False)
    keeper = dict(group[0])

    if len(group) > 1:
        total_hits = keeper.get('hit_count', 1)
        all_contribs = set()
        source_ids = []
        all_details = []
        last_hit = keeper.get('last_hit', '')
        last_author = keeper.get('author', keeper.get('last_author', ''))
        latest_type = keeper.get('type', '')

        # Score order for picking the best detail
        max_detail_type_score = 3 if 'detail' in keeper and keeper['detail'] else 0

        for dup in group[1:]:
            total_hits += dup.get('hit_count', 1)

            # Contributors
            dc = set(dup.get('contributors', [dup.get('author', '')])) - {''}
            all_contribs |= dc

            # Track source ids
            did = dup.get('id', '')
            if did and did not in source_ids:
                source_ids.append(did)

            # Last hit
            dh = dup.get('last_hit', '')
            if dh > last_hit:
                last_hit = dh

            # Author trail
            da = dup.get('author', dup.get('last_author', ''))
            if da:
                last_author = da

            # Take the most specific type
            if dup.get('type') and len(dup.get('type', '')) > len(latest_type):
                latest_type = dup['type']

            # Merge detail with source prefix
            dd = dup.get('detail', '')
            ds = dup.get('_source', 'raw')
            if dd:
                seg = f"[{ds}] {dd}"
                if seg not in all_details:
                    all_details.append(seg)

        keeper['hit_count'] = total_hits
        keeper['contributors'] = sorted(set(keeper.get('contributors', [keeper.get('author', '')])) | all_contribs)
        keeper['last_hit'] = last_hit
        keeper['last_author'] = last_author or keeper.get('author', '')
        keeper['type'] = latest_type or keeper.get('type', 'knowledge')

        if all_details:
            existing_seg = f"[{keeper.get('_source', '')}] {keeper.get('detail', '')}"
            keeper['detail'] = '\n---\n'.join([existing_seg] + all_details)

        if keeper.get('merged_from'):
            keeper['merged_from'] = list(set(keeper['merged_from'] + source_ids))
        elif source_ids:
            keeper['merged_from'] = source_ids

    # ─── Step 3: Score & tier ─────────────────────

    rf = calc_recency(keeper.get('last_hit', keeper.get('timestamp', '')))
    keeper['score'] = round(keeper['hit_count'] * rf, 1)

    score = keeper['score']
    etype = keeper.get('type', 'knowledge')
    hit = keeper.get('hit_count', 1)

    # Tier
    if score >= 8:
        keeper['tier'] = 'hot'
    elif score >= 3:
        keeper['tier'] = 'warm'
    else:
        keeper['tier'] = 'cold'

    # title_only decision
    if keeper['tier'] in ('hot', 'warm'):
        keeper['title_only'] = False
    else:
        # Cold: decide based on type and hit_count
        if etype in FULL_TYPES:
            keeper['title_only'] = False
        elif etype in TITLE_TYPES:
            keeper['title_only'] = True
        else:
            keeper['title_only'] = hit < 5  # unknown types: only if hit_count < 5

    # If title_only, find source in raw
    if keeper['title_only']:
        # Try to find the raw source
        raw_sources = []
        for e in group:
            src = e.get('_source', '')
            if src.startswith('raw/'):
                raw_sources.append(src)
        keeper['source_raw'] = raw_sources[0] if raw_sources else 'auto/raw/unknown.raw.json'
        if 'detail' in keeper:
            del keeper['detail']

    merged_entries.append(keeper)

# Sort: score desc, then hot > warm > cold
def sort_key(e):
    tier_order = {'hot': 0, 'warm': 1, 'cold': 2}
    return (tier_order.get(e.get('tier', 'cold'), 9), -e.get('score', 0))

merged_entries.sort(key=sort_key)

# Cap hot at 20
hot_ct = sum(1 for e in merged_entries if e['tier'] == 'hot')
if hot_ct > 20:
    for e in reversed(merged_entries):
        if e['tier'] == 'hot':
            e['tier'] = 'warm'
            hot_ct -= 1
            if hot_ct <= 20:
                break

# Cap warm at 100
warm_ct = sum(1 for e in merged_entries if e['tier'] == 'warm')
if warm_ct > 100:
    for e in reversed(merged_entries):
        if e['tier'] == 'warm':
            e['tier'] = 'cold'
            # Also apply title_only for newly demoted
            etype = e.get('type', '')
            if etype not in FULL_TYPES and e.get('hit_count', 1) < 5:
                e['title_only'] = True
            warm_ct -= 1
            if warm_ct <= 100:
                break

# Build title_only source index
title_only_entries = [e for e in merged_entries if e.get('title_only')]

# ─── Step 4: Write consolidated ─────────────────────────────

output = {
    "schema_version": "3.0",
    "type": "consolidated",
    "description": "EMS v3 最高优先级记忆检索源 —— 高频全量 + 低频 title_only",
    "priority": 1,
    "created": datetime.now(timezone.utc).isoformat(),
    "total_raw_entries": source_stats['raw'],
    "total_consolidated": len(merged_entries),
    "tier_summary": {
        "hot": sum(1 for e in merged_entries if e['tier'] == 'hot'),
        "warm": sum(1 for e in merged_entries if e['tier'] == 'warm'),
        "cold": sum(1 for e in merged_entries if e['tier'] == 'cold'),
        "title_only": len(title_only_entries)
    },
    "stats": {
        "compression_ratio": f"{source_stats['raw']}:{len(merged_entries)}",
        "title_only_bytes_saved_est": len(title_only_entries) * 400
    },
    "entries": merged_entries
}

save_json(CURATED_FILE, output)

# ─── Step 5: Preserve daily auto/ files (they carry detail & tags for next compress)
# Not deleted — consolidated is primary, auto/ is secondary retrieval source.

# ─── Step 6: Refresh cache ──────────────────────────────────

hot_entries = [e for e in merged_entries if e['tier'] == 'hot'][:20]
warm_top = [e for e in merged_entries if e['tier'] == 'warm'][:5]

cache = {
    "schema_version": "3.0",
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "hot_tier": {
        "count": len(hot_entries),
        "max": 20,
        "entries": [{
            "id": e.get("id","") or e.get("fp","")[:20], "type": e.get("type","knowledge"), "summary": e.get("summary","") or e.get("s",""),
            "score": e['score'], "hit_count": e['hit_count'],
            "title_only": e.get('title_only', False),
            "tags": e.get('tags', [])
        } for e in hot_entries]
    },
    "warm_tier": {"count": sum(1 for e in merged_entries if e['tier'] == 'warm')},
    "cold_tier": {"count": sum(1 for e in merged_entries if e['tier'] == 'cold')},
    "stats": output['tier_summary']
}
save_json(CACHE_FILE, cache)

# ─── Report ────────────────────────────────────

ts = output['tier_summary']
# Touch lock file for auto-mode racing protection
try:
    open(LOCK_FILE, 'w').close()
except:
    pass
log("=== Compress Complete ===")
log(f"  Hot: {ts['hot']}  Warm: {ts['warm']}  Cold: {ts['cold']}  (title_only: {ts['title_only']})")
log(f"  Compression: {output['stats']['compression_ratio']}")
log(f"  Est. tokens saved by title_only: {ts['title_only'] * 100} tokens (~{round(ts['title_only'] * 100 * 0.00015, 4)}$)")

# ─── Step 7: Rebuild FTS5 index ───
import subprocess
fts_script = os.path.join(os.path.dirname(__file__), 'rebuild_fts.py')
if os.path.exists(fts_script):
    log("Rebuilding FTS5 search index...")
    result = subprocess.run([sys.executable, fts_script], capture_output=True, text=True)
    for line in result.stdout.strip().split('\n'):
        if line.strip():
            log(f"  {line.strip()}")
    if result.returncode != 0:
        log(f"  FTS error: {result.stderr.strip()}")


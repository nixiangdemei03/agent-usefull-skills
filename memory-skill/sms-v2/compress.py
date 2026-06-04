#!/usr/bin/env python3
"""
SMS v2 — Consolidate & Compress
读取所有 auto/ 条目 → 按 fingerprint 合并 → 输出 curated/consolidated.json
该文件成为最高优先级检索目标，未命中再回退到 auto/ 日志文件。
"""
import json, os, sys
from datetime import datetime, timezone
from collections import defaultdict

MEMORY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AUTO_DIR = os.path.join(MEMORY_DIR, 'auto')
CURATED_FILE = os.path.join(MEMORY_DIR, 'curated', 'consolidated.json')
CONSOLIDATED_LOCK = os.path.join(MEMORY_DIR, 'curated', '.consolidated_lock')

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def calc_recency(last_hit_str):
    """Calculate recency factor (1-3)"""
    try:
        last_ts = datetime.fromisoformat(last_hit_str).timestamp()
    except:
        return 1.0
    diff_days = (datetime.now().timestamp() - last_ts) / 86400
    if diff_days <= 1:    return 3.0
    elif diff_days <= 7:  return 1.5
    elif diff_days <= 30: return 1.0
    else:                 return 0.5

def build_fingerprint(entry):
    """Compute or retrieve fingerprint"""
    fp = entry.get('fingerprint', '')
    if fp:
        return fp
    tags = sorted(entry.get('tags', []) or [])
    summary = (entry.get('summary', '') or '').strip()[:50].lower()
    return ','.join(tags) + '|' + summary

# ── Step 1: Collect all auto entries ──
print("[SMS-compress] Reading auto/ entries...")
all_entries = []
source_files = []

for fname in sorted(os.listdir(AUTO_DIR)):
    if not fname.endswith('.json'):
        continue
    fpath = os.path.join(AUTO_DIR, fname)
    try:
        with open(fpath) as f:
            entries = json.load(f)
    except:
        continue
    for e in entries:
        if e.get('tier') != 'archive':
            all_entries.append(e)
            source_files.append(fname)

print(f"[SMS-compress] Collected {len(all_entries)} entries from {len(set(source_files))} files")

# ── Step 2: Group by fingerprint ──
groups = defaultdict(list)
for e in all_entries:
    fp = build_fingerprint(e)
    groups[fp].append(e)

print(f"[SMS-compress] Grouped into {len(groups)} unique fingerprints")

# ── Step 3: Merge each group ──
consolidated = []

for fp, group in groups.items():
    # Sort by hit_count desc (strongest wins)
    group.sort(key=lambda e: e.get('hit_count', 1), reverse=True)
    keeper = dict(group[0])  # deep-ish copy

    if len(group) > 1:
        # Merge all dups into keeper
        total_hit = keeper.get('hit_count', 1)
        all_contribs = set(keeper.get('contributors', [keeper.get('author', 'unknown')]))
        source_ids = [keeper['id']]
        last_hit = keeper.get('last_hit', '')
        merged_details = []

        if keeper.get('detail'):
            merged_details.append(f"[{keeper.get('author', 'unknown')}] {keeper['detail']}")

        for dup in group[1:]:
            if dup.get('tier') == 'archive':
                continue
            total_hit += dup.get('hit_count', 1)
            dup_contribs = set(dup.get('contributors', [dup.get('author', 'unknown')]))
            all_contribs |= dup_contribs
            source_ids.append(dup['id'])

            if dup.get('last_hit', '') > last_hit:
                last_hit = dup['last_hit']

            dup_detail = dup.get('detail', '')
            dup_author = dup.get('author', dup.get('last_author', 'unknown'))
            if dup_detail:
                seg = f"[{dup_author}] {dup_detail}"
                if seg not in merged_details:
                    merged_details.append(seg)

        keeper['hit_count'] = total_hit
        keeper['contributors'] = sorted(all_contribs)
        keeper['merged_from'] = source_ids
        keeper['last_hit'] = last_hit
        keeper['detail'] = '\n---\n'.join(merged_details) if merged_details else ''

    # Recalculate score with combined hit_count
    rf = calc_recency(keeper.get('last_hit', keeper.get('timestamp', now_iso())))
    keeper['score'] = round(keeper['hit_count'] * rf, 1)
    keeper['tier'] = 'hot' if keeper['score'] >= 8 else 'warm'

    # Add consolidated meta
    keeper['_source_count'] = len(group)
    consolidated.append(keeper)

# Sort consolidated by score descending
consolidated.sort(key=lambda e: e.get('score', 0), reverse=True)

# Cap at 50 entries to keep it lean
if len(consolidated) > 50:
    print(f"[SMS-compress] Capping consolidated at 50 entries (had {len(consolidated)})")
    consolidated = consolidated[:50]

# ── Step 4: Build the consolidated file ──
output = {
    "schema_version": "2.0",
    "type": "consolidated",
    "description": "SMS 最高优先级记忆检索源 —— 所有按 fingerprint 去重合并后的条目，按 score 排序",
    "priority": 1,
    "created": now_iso(),
    "total_original_entries": len(all_entries),
    "total_consolidated_entries": len(consolidated),
    "compression_ratio": f"{len(all_entries)}:{len(consolidated)}",
    "source_files": sorted(set(source_files)),
    "entries": consolidated
}

# ── Step 5: Write ──
os.makedirs(os.path.dirname(CURATED_FILE), exist_ok=True)
with open(CURATED_FILE, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"[SMS-compress] ✅ Written to curated/consolidated.json")
print(f"[SMS-compress]    Original: {len(all_entries)} entries → Consolidated: {len(consolidated)} entries")
print(f"[SMS-compress]    Compression ratio: {output['compression_ratio']}")
print(f"[SMS-compress]    Top score: {consolidated[0]['score'] if consolidated else 0}, Bottom: {consolidated[-1]['score'] if consolidated else 0}")

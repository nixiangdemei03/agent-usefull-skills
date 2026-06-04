#!/bin/bash
# SMS v2 — Cache Refresh Script
# 按 tier 生成 Hot 层摘要 + score-sorted 索引

MEMORY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CACHE_FILE="$MEMORY_DIR/cache/memory_cache.json"
AUTO_DIR="$MEMORY_DIR/auto"

echo "[SMS-v2] Refreshing cache at $(date)"

python3 -c "
import json, os
from datetime import datetime, timezone

auto_dir = '$AUTO_DIR'
cache_path = '$CACHE_FILE'

all_entries = []
for fname in sorted(os.listdir(auto_dir)):
    if not fname.endswith('.json'):
        continue
    with open(os.path.join(auto_dir, fname)) as f:
        entries = json.load(f)
    all_entries.extend(entries)

# sort by score descending
all_entries.sort(key=lambda e: e.get('score', 0), reverse=True)

hot = [e for e in all_entries if e.get('tier') == 'hot']
warm = [e for e in all_entries if e.get('tier') == 'warm']
cold_count = len([e for e in all_entries if e.get('tier') == 'cold'])

cache = {
    'schema_version': '2.0',
    'last_updated': datetime.now(timezone.utc).isoformat(),
    'hot_tier': {
        'count': len(hot),
        'max': 20,
        'entries': [{
            'id': e['id'],
            'type': e['type'],
            'summary': e['summary'],
            'score': e.get('score', 0),
            'hit_count': e.get('hit_count', 1),
            'tags': e.get('tags', []),
            'last_hit': e.get('last_hit', '')
        } for e in hot[:20]]
    },
    'warm_tier': {
        'count': len(warm),
        'top': [{
            'id': e['id'],
            'type': e['type'],
            'summary': e['summary'],
            'score': e.get('score', 0)
        } for e in warm[:5]]
    },
    'cold_tier': {
        'count': cold_count
    },
    'stats': {
        'total_entries': len(all_entries),
        'hot': len(hot),
        'warm': len(warm),
        'cold': cold_count
    }
}

with open(cache_path, 'w') as f:
    json.dump(cache, f, indent=2, ensure_ascii=False)

print(f'Cache: {len(hot)} hot + {len(warm)} warm + {cold_count} cold = {len(all_entries)} total')
"

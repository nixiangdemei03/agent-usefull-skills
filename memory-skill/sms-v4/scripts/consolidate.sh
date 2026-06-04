#!/bin/bash
# EMS v2 — Consolidation Script
# score重算 → tier再分配 → Git同步去重 → 报告
# 用法: bash consolidate.sh [--git-pull [仓库URL]]

MEMORY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AUTO_DIR="$MEMORY_DIR/auto"
CURATED_DIR="$MEMORY_DIR/curated"
INDEX_FILE="$MEMORY_DIR/index.json"
CACHE_FILE="$MEMORY_DIR/cache/memory_cache.json"

AUTHOR="${SMS_AUTHOR:-$(hostname)}"
GIT_PULL=false
GIT_REPO=""

# Parse args
for arg in "$@"; do
  if [ "$arg" = "--git-pull" ]; then
    GIT_PULL=true
  elif [ "$GIT_PULL" = true ] && [ -z "$GIT_REPO" ]; then
    GIT_REPO="$arg"
  fi
done

echo "[EMS-v2] ╔══════════════════════════════════════╗"
echo "[EMS-v2] ║   Consolidation Start                ║"
echo "[EMS-v2] ╚══════════════════════════════════════╝"
echo "[EMS-v2] Author: $AUTHOR"
echo "[EMS-v2] Date: $(date)"
echo ""

# ── Step 0: Git pull (if enabled) ────────────────────────────
if $GIT_PULL; then
  if [ -d "$MEMORY_DIR/.git" ]; then
    echo "[EMS-v2] ── Git pull ──"
    git -C "$MEMORY_DIR" pull --rebase 2>&1 | sed 's/^/  /'
    echo ""
  elif [ -n "$GIT_REPO" ]; then
    echo "[EMS-v2] ── Git clone ──"
    mv "$MEMORY_DIR" "${MEMORY_DIR}_backup"
    git clone "$GIT_REPO" "$MEMORY_DIR" 2>&1 | sed 's/^/  /'
    # Re-merge backup entries into cloned repo
    if [ -d "${MEMORY_DIR}_backup/auto" ]; then
      cp -r "${MEMORY_DIR}_backup/auto"/*.json "$MEMORY_DIR/auto/" 2>/dev/null
    fi
    echo ""
  else
    echo "[EMS-v2] ⚠️  --git-pull set but no .git dir and no repo URL given"
    echo "[EMS-v2]    Set EMS_GIT_REPO env or pass URL: --git-pull https://..."
    echo ""
  fi
fi

# ── Step 1: Score all entries ────────────────────────────────
echo "[EMS-v2] ── Scoring entries ──"

python3 -c "
import json, os
from datetime import datetime, timezone

now = datetime.now(timezone.utc).timestamp()
auto_dir = '$AUTO_DIR'
author = '$AUTHOR'
hot = warm = cold = 0

for fname in sorted(os.listdir(auto_dir)):
    if not fname.endswith('.json'):
        continue
    fpath = os.path.join(auto_dir, fname)
    try:
        with open(fpath) as f:
            entries = json.load(f)
    except:
        continue

    changed = False
    for e in entries:
        if e.get('tier') == 'archive':
            continue

        # ensure v2 fields
        e['hit_count'] = e.get('hit_count', 1) or 1
        e['last_hit'] = e.get('last_hit', e.get('timestamp', now))
        if 'author' not in e or not e['author']:
            e['author'] = author
            changed = True
        if 'contributors' not in e or not e['contributors']:
            e['contributors'] = [e['author']]
            changed = True

        # calc recency
        try:
            last_ts = datetime.fromisoformat(e['last_hit']).timestamp()
        except:
            last_ts = now
        diff_days = (now - last_ts) / 86400
        if diff_days <= 1:    rf = 3.0
        elif diff_days <= 7:  rf = 1.5
        elif diff_days <= 30: rf = 1.0
        else:                 rf = 0.5

        score = e['hit_count'] * rf
        e['score'] = round(score, 1)

        # assign tier
        if score >= 8:
            e['tier'] = 'hot'
            hot += 1
        elif score >= 3:
            e['tier'] = 'warm'
            warm += 1
        else:
            e['tier'] = 'cold'
            cold += 1

    if changed:
        with open(fpath, 'w') as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

print(f'hot={hot} warm={warm} cold={cold}')
"

# ── Step 2: Cross-file dedup via fingerprint ──────────────────
echo "[EMS-v2] ── Cross-file dedup ──"

python3 -c "
import json, os
from collections import defaultdict

auto_dir = '$AUTO_DIR'
author = '$AUTHOR'

# Collect all entries by fingerprint
fp_map = defaultdict(list)
all_entries = []

for fname in sorted(os.listdir(auto_dir)):
    if not fname.endswith('.json'):
        continue
    fpath = os.path.join(auto_dir, fname)
    try:
        with open(fpath) as f:
            entries = json.load(f)
    except:
        continue
    all_entries.append((fname, fpath, entries))
    for e in entries:
        fp = e.get('fingerprint', '')
        if fp and e.get('tier') != 'archive':
            fp_map[fp].append(e)

merged_count = 0
for fp, group in fp_map.items():
    if len(group) <= 1:
        continue

    # Sort by hit_count desc (the strongest entry wins)
    group.sort(key=lambda e: e.get('hit_count', 1), reverse=True)
    keeper = group[0]

    for dup in group[1:]:
        if dup.get('tier') == 'archive':
            continue

        # Merge hit_count
        keeper['hit_count'] = keeper.get('hit_count', 1) + dup.get('hit_count', 1)

        # Merge contributors
        k_contribs = set(keeper.get('contributors', [keeper.get('author', '')]))
        d_contribs = set(dup.get('contributors', [dup.get('author', '')]))
        keeper['contributors'] = sorted(k_contribs | d_contribs)

        # Update last_author
        dup_author = dup.get('author', dup.get('last_author', ''))
        if dup_author and dup_author not in k_contribs:
            keeper['last_author'] = dup_author

        # Merge detail with author prefix
        old_detail = keeper.get('detail', '')
        dup_detail = dup.get('detail', '')
        dup_author_name = dup.get('author', 'unknown')
        if dup_detail and dup_detail not in old_detail:
            new_seg = f'[{dup_author_name}] {dup_detail}'
            if new_seg not in old_detail:
                keeper['detail'] = (old_detail + '\n---\n' + new_seg).strip()

        # Track merged_from
        if 'merged_from' not in keeper or not keeper['merged_from']:
            keeper['merged_from'] = []
        if dup['id'] not in keeper['merged_from']:
            keeper['merged_from'].append(dup['id'])

        # Update last_hit (take the most recent)
        if dup.get('last_hit', '') > keeper.get('last_hit', ''):
            keeper['last_hit'] = dup['last_hit']

        # Mark dup as archive
        dup['tier'] = 'archive'
        dup['summary'] = f'[merged→{keeper[\"id\"]}] ' + dup.get('summary', '')[:60]
        dup['detail'] = ''
        dup['hit_count'] = 0
        merged_count += 1

    # Rewrite keeper's score
    rf = 1.0
    diff_days = (datetime.now().timestamp() - datetime.fromisoformat(keeper['last_hit']).timestamp()) / 86400
    if diff_days <= 1:    rf = 3.0
    elif diff_days <= 7:  rf = 1.5
    elif diff_days <= 30: rf = 1.0
    keeper['score'] = round(keeper['hit_count'] * rf, 1)

# Write all files back
for fname, fpath, entries in all_entries:
    with open(fpath, 'w') as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

print(f'merged {merged_count} duplicate entries')
"

# ── Step 3: Hot / Warm cap ──────────────────────────────────
echo "[EMS-v2] ── Tier cap (Hot≤20, Warm≤100) ──"

python3 -c "
import json, os
from datetime import datetime

auto_dir = '$AUTO_DIR'

# Collect all entries
all_entries = []
for fname in sorted(os.listdir(auto_dir)):
    if not fname.endswith('.json'):
        continue
    with open(os.path.join(auto_dir, fname)) as f:
        entries = json.load(f)
    all_entries.extend(entries)

# Hot cap: promote top 20 by score, demote rest to warm
hot = [e for e in all_entries if e.get('tier') == 'hot']
hot.sort(key=lambda e: e.get('score', 0), reverse=True)

if len(hot) > 20:
    excess_ids = {e['id'] for e in hot[20:]}
    for fname in sorted(os.listdir(auto_dir)):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(auto_dir, fname)
        with open(fpath) as f:
            entries = json.load(f)
        changed = False
        for e in entries:
            if e['id'] in excess_ids and e.get('tier') == 'hot':
                e['tier'] = 'warm'
                changed = True
        if changed:
            with open(fpath, 'w') as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f'demoted {len(excess_ids)} hot→warm (cap 20)')
else:
    # If hot not full, promote top warm entries
    deficit = 20 - len(hot)
    warm = [e for e in all_entries if e.get('tier') == 'warm']
    warm.sort(key=lambda e: e.get('score', 0), reverse=True)
    promoted = warm[:deficit]
    promoted_ids = {e['id'] for e in promoted}
    for fname in sorted(os.listdir(auto_dir)):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(auto_dir, fname)
        with open(fpath) as f:
            entries = json.load(f)
        changed = False
        for e in entries:
            if e['id'] in promoted_ids and e.get('tier') == 'warm':
                e['tier'] = 'hot'
                changed = True
        if changed:
            with open(fpath, 'w') as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
    if promoted:
        print(f'promoted {len(promoted)} warm→hot (filling cap)')
    else:
        print(f'hot: {len(hot)}')

# Warm cap at 100
warm = [e for e in all_entries if e.get('tier') == 'warm']
warm.sort(key=lambda e: e.get('score', 0), reverse=True)
if len(warm) > 100:
    excess_ids = {e['id'] for e in warm[100:]}
    for fname in sorted(os.listdir(auto_dir)):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(auto_dir, fname)
        with open(fpath) as f:
            entries = json.load(f)
        changed = False
        for e in entries:
            if e['id'] in excess_ids and e.get('tier') == 'warm':
                e['tier'] = 'cold'
                changed = True
        if changed:
            with open(fpath, 'w') as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f'demoted {len(excess_ids)} warm→cold (cap 100)')
else:
    print(f'warm: {len(warm)} (under cap 100)')
"

# ── Step 4: Summary ──────────────────────────────────────────
echo ""
echo "[EMS-v2] ── Tier Summary ──"

python3 "$MEMORY_DIR/scripts/_summary.py" "$AUTO_DIR"

echo ""
echo "[EMS-v2] ── Cache refresh ──"
bash "$MEMORY_DIR/scripts/cache_refresh.sh"
if $GIT_PULL && [ -d "$MEMORY_DIR/.git" ]; then
  echo ""
  echo "[EMS-v2] ── Git push ──"
  git -C "$MEMORY_DIR" add -A 2>&1 | sed 's/^/  /'
  git -C "$MEMORY_DIR" commit -m "ems-v2 consolidate $(date +%Y-%m-%d-%H%M)" 2>&1 | sed 's/^/  /'
  git -C "$MEMORY_DIR" push 2>&1 | sed 's/^/  /'
fi

echo ""
echo "[EMS-v2] ── Consolidation complete ──"
echo "[EMS-v2] $(date)"

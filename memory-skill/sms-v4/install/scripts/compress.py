#!/usr/bin/env python3
"""
SMS v4 — Compress Engine v3

── 变更历史 ──
v1 -> v2 (2026-06-05): 新评分公式, 闲时检测, 交换式降级, Cold 保留
v2 -> v3 (2026-06-05): 半衰期 14→21天 (统一 λ), Warm 饱和度门限,
                        SQLite 复用替代 full_detail.json, 容错闲时采样,
                        Warm 溢出消化, 旧条目补 importance
"""
import json, os, sys, glob, math, subprocess, sqlite3
from datetime import datetime, timezone
from collections import defaultdict

MEMORY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AUTO_DIR = os.path.join(MEMORY_DIR, 'auto')
RAW_DIR = os.path.join(AUTO_DIR, 'raw')
CURATED_DIR = os.path.join(MEMORY_DIR, 'curated')
CURATED_FILE = os.path.join(CURATED_DIR, 'consolidated.json')
CACHE_FILE = os.path.join(MEMORY_DIR, 'cache', 'memory_cache.json')
LOCK_FILE = os.path.join(MEMORY_DIR, '.last_compress')
IDLE_FILE = '/mnt/c/Users/64608/.claude/idle_state.txt'   # 由 idle_monitor.ps1 写入
IDLE_COUNTER = os.path.join(MEMORY_DIR, '.idle_counter')    # WSL 侧容错计数器
FTS_DB = os.path.join(MEMORY_DIR, 'fts', 'memory.db')       # 冷数据 detail 存储

HALF_LIFE_DAYS = 21     # 统一半衰期 → 21天衰减50%
HOT_CAP = 20
WARM_CAP = 100
WARM_SATURATION = 90    # Warm 满 90% 时才开始 Warm→Cold 降级
IDLE_THRESHOLD = 300    # 5分钟
IDLE_SAMPLES_NEEDED = 6 # 连续 6 次采样才算闲时 (避免误触)

FULL_TYPES = {'knowledge', 'decision', 'insight', 'failure'}
TITLE_TYPES = {'event', 'context_switch', 'chat', 'chat_insight', 'preference'}

def log(msg): print(f"[SMS-v4] {msg}")

# ═══════════════════════════════════════════════════════════════
#  闲时检测 (v3: 文件读取 + PowerShell 备选 + 容错采样)
# ═══════════════════════════════════════════════════════════════

def read_idle_file():
    """从 idle_monitor.ps1 写入的文件读取空闲秒数"""
    try:
        with open(IDLE_FILE) as f:
            val = float(f.read().strip())
            return val
    except:
        return -1.0

def check_windows_idle_seconds():
    """尝试多种方式获取 Windows 用户空闲秒数"""
    # 方案 A: 读 idle_monitor.ps1 写入的文件 (推荐)
    val = read_idle_file()
    if val >= 0:
        return val
    # 方案 B: 直接调 PowerShell (备选)
    ps_candidates = ['powershell.exe', '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe']
    ps_cmd = 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SystemInformation]::IdleTime.TotalSeconds'
    for ps_exe in ps_candidates:
        try:
            result = subprocess.run([ps_exe, '-Command', ps_cmd], capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except:
            continue
    return -1.0

def check_idle_with_counter():
    """
    容错采样: 连续 IDLE_SAMPLES_NEEDED 次都空闲才算闲时。
    读取上一个 idle_counter 值，和当前比对判断。
    """
    idle_seconds = check_windows_idle_seconds()
    if idle_seconds < 0:
        log("  Idle detect unavailable — skip")
        return False

    is_idle_now = idle_seconds >= IDLE_THRESHOLD

    # 读取上次的计数
    prev_count = 0
    prev_idle = False
    if os.path.exists(IDLE_COUNTER):
        try:
            prev_str = open(IDLE_COUNTER).read().strip()
            parts = prev_str.split(',')
            prev_count = int(parts[0])
            prev_idle = parts[1] == '1'
        except:
            pass

    if is_idle_now:
        if prev_idle:
            # 连续空闲 → 计数+1
            count = prev_count + 1
            if count >= IDLE_SAMPLES_NEEDED:
                open(IDLE_COUNTER, 'w').write(f'{count},1')
                log(f"  User idle: {idle_seconds:.0f}s (confirm #{count})")
                return True
        else:
            count = 0  # 从 0 开始计数 (不是 1)
        open(IDLE_COUNTER, 'w').write(f'{count},1')
        log(f"  User idle start ({idle_seconds:.0f}s), need {IDLE_SAMPLES_NEEDED} samples")
    else:
        open(IDLE_COUNTER, 'w').write('0,0')
        log(f"  User active (idle: {idle_seconds:.0f}s) — reset counter")

    return False

# ═══════════════════════════════════════════════════════════════
#  热度公式 Score = I × e^(-λt) × log(f+1), half_life=21天
# ═══════════════════════════════════════════════════════════════

def calc_score(importance, hit_count, days_since_last_hit):
    """
    Score = I × e^(-λt) × log(1 + f)

    统一 λ = ln(2) / 21  (half_life = 21天)
    14/28/42 天只是人类可读的活性标签，非三个 λ 值:
      - <14 天: 高活跃
      - 14-28 天: 中活跃
      - 28-42 天: 低活跃
      - >42 天: 弱活跃
    分数随连续函数 e^(-λt) 平滑衰减，无跳跃。
    """
    i = max(1, min(10, importance if importance else 5))
    lam = math.log(2) / HALF_LIFE_DAYS  # ≈ 0.033/天
    decay = math.exp(-lam * max(0, days_since_last_hit))
    freq = math.log(1 + max(0, hit_count))
    return round(i * decay * freq, 2)

def calc_days_since(last_hit_str):
    if not last_hit_str:
        return 999
    try:
        last = datetime.fromisoformat(last_hit_str)
        if last.tzinfo is not None:
            last = last.astimezone(timezone.utc)
        else:
            last = last.replace(tzinfo=timezone.utc)
        diff = (datetime.now(timezone.utc) - last).total_seconds() / 86400
        return max(0, diff)
    except:
        return 999

def build_fingerprint(e):
    fp = e.get('fingerprint', '') or e.get('fp', '')
    if fp:
        return fp
    tags = sorted(e.get('tags', []) or [])
    s = (e.get('summary', '') or e.get('s', '') or '').strip()[:50].lower()
    return ','.join(tags) + '|' + s

def get_importance_for_old_entry(e):
    """旧条目补 importance: hot=7, warm=5, cold=3"""
    imp = e.get('importance', 0)
    if imp and imp > 0:
        return imp
    tier = e.get('tier', 'warm')
    return {'hot': 7, 'warm': 5, 'cold': 3}.get(tier, 5)

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

def latest_mtime(directory, pattern='*.json'):
    files = glob.glob(os.path.join(directory, pattern))
    if not files:
        return 0
    return max(os.path.getmtime(f) for f in files)

# ═══════════════════════════════════════════════════════════════
#  Auto Mode — 闲时压缩 (v3: 容错采样)
# ═══════════════════════════════════════════════════════════════

AUTO_MODE = '--auto' in sys.argv

if AUTO_MODE:
    now_ts = datetime.now().timestamp()

    last_compress = os.path.getmtime(LOCK_FILE) if os.path.exists(LOCK_FILE) else 0
    if now_ts - last_compress < 60:
        sys.exit(0)

    if not check_idle_with_counter():
        sys.exit(0)

    if os.path.exists(CURATED_FILE):
        consolidated_mtime = os.path.getmtime(CURATED_FILE)
        if consolidated_mtime >= latest_mtime(RAW_DIR) and consolidated_mtime >= latest_mtime(AUTO_DIR):
            open(LOCK_FILE, 'w').close()
            sys.exit(0)

    log("Auto: PROCEED (idle confirmed + new data)")

# ═══════════════════════════════════════════════════════════════
#  Step 0: Dirty Check
# ═══════════════════════════════════════════════════════════════

log("=== Compress Start ===")
os.makedirs(RAW_DIR, exist_ok=True)

if not AUTO_MODE:
    if os.path.exists(CURATED_FILE):
        if os.path.getmtime(CURATED_FILE) >= latest_mtime(RAW_DIR) and os.path.getmtime(CURATED_FILE) >= latest_mtime(AUTO_DIR):
            log("Dirty check: SKIP")
            open(LOCK_FILE, 'w').close()
            sys.exit(0)
    log("Dirty check: NEED COMPRESS")

# ═══════════════════════════════════════════════════════════════
#  Step 1: Collect all entries
# ═══════════════════════════════════════════════════════════════

all_entries = []
source_stats = defaultdict(int)

for fname in sorted(os.listdir(RAW_DIR)):
    if not fname.endswith('.raw.json'):
        continue
    entries = load_json(os.path.join(RAW_DIR, fname))
    if not entries:
        continue
    for e in entries:
        if isinstance(e, dict):
            raw_date = fname[:10]
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
                'importance': e.get('importance', 5),
                'detail': e.get('detail', ''),
                'tags': e.get('tags', []),
                'tier': e.get('tier', ''),
                'title_only': False,
            }
            all_entries.append(norm)
            source_stats['raw'] += 1

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

consolidated = load_json(CURATED_FILE)
if consolidated and consolidated.get('entries'):
    for e in consolidated['entries']:
        if e.get('tier') == 'archive':
            continue
        e['_source'] = e.get('source_raw', 'curated/consolidated.json')
        all_entries.append(e)
        source_stats['consolidated'] += 1

log(f"Collected: raw={source_stats['raw']} auto={source_stats['auto']} consolidated={source_stats['consolidated']} total={len(all_entries)}")

# ═══════════════════════════════════════════════════════════════
#  Step 2: Fingerprint group & merge
# ═══════════════════════════════════════════════════════════════

groups = defaultdict(list)
for e in all_entries:
    fp = build_fingerprint(e)
    if fp:
        groups[fp].append(e)

log(f"Fingerprint groups: {len(groups)}")

merged_entries = []
for fp, group in groups.items():
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
        importance = get_importance_for_old_entry(keeper)

        for dup in group[1:]:
            total_hits += dup.get('hit_count', 1)
            dc = set(dup.get('contributors', [dup.get('author', '')])) - {''}
            all_contribs |= dc
            did = dup.get('id', '')
            if did and did not in source_ids:
                source_ids.append(did)
            dh = dup.get('last_hit', '')
            if dh > last_hit:
                last_hit = dh
            da = dup.get('author', dup.get('last_author', ''))
            if da:
                last_author = da
            if dup.get('type') and len(dup.get('type', '')) > len(latest_type):
                latest_type = dup['type']
            imp = dup.get('importance', 0)
            if imp > importance:
                importance = imp
            elif imp == 0:
                # 旧条目没 importance → 按 tier 推测
                imp_tier = get_importance_for_old_entry(dup)
                if imp_tier > importance:
                    importance = imp_tier
            dd = dup.get('detail', '')
            ds = dup.get('_source', 'raw')
            if dd:
                seg = f"[{ds}] {dd}"
                if seg not in all_details:
                    all_details.append(seg)

        keeper['hit_count'] = total_hits
        keeper['importance'] = importance
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
    else:
        # 单条记录也补 importance
        if not keeper.get('importance'):
            keeper['importance'] = get_importance_for_old_entry(keeper)

    # 评分
    days = calc_days_since(keeper.get('last_hit', keeper.get('timestamp', '')))
    imp = keeper.get('importance', 5)
    hits = keeper['hit_count']
    keeper['score'] = calc_score(imp, hits, days)
    merged_entries.append(keeper)

# ═══════════════════════════════════════════════════════════════
#  Step 3: 交换式降级 (v3: Warm 饱和度门限 + 溢出消化)
# ═══════════════════════════════════════════════════════════════

# 记录旧 tier
old_tier_map = {e.get('id', ''): e.get('tier', '') for e in merged_entries}

merged_entries.sort(key=lambda e: -e.get('score', 0))
total = len(merged_entries)

# 顶级分配 → 算清数量
hot_count = min(HOT_CAP, total)
# Warm: 如果总条目不够填满 warm, 则 warm = 剩余, cold = 0
remaining = total - hot_count
warm_count = min(WARM_CAP, remaining)
cold_count = remaining - warm_count

warm_saturation = 0
if warm_count > 0:
    warm_saturation = round(warm_count / WARM_CAP * 100, 0)

# 如果 Warm 饱和度 < 90%，Cold 降级被抑制 → warm 扩张
if warm_saturation < WARM_SATURATION and cold_count > 0:
    # 扩张 warm 吞掉 cold（不踢出到 cold）
    warm_count += cold_count
    cold_count = 0

# 如果 Warm 溢出（新增 hot 导致 warm 超 cap），消化 overflow
overflow = max(0, warm_count - WARM_CAP)
if overflow > 0:
    # 放入 cold
    warm_count = WARM_CAP
    cold_count += overflow

# 按 count 分配 tier
for i in range(total):
    e = merged_entries[i]
    if i < hot_count:
        e['tier'] = 'hot'
    elif i < hot_count + warm_count:
        e['tier'] = 'warm'
    else:
        e['tier'] = 'cold'

# 交换统计
demoted_hot = 0
promoted_warm = 0
demoted_warm = 0
for e in merged_entries:
    old = old_tier_map.get(e.get('id', ''), '')
    if old == 'hot' and e['tier'] == 'warm':
        demoted_hot += 1
    elif old == 'warm' and e['tier'] == 'hot':
        promoted_warm += 1
    elif old == 'warm' and e['tier'] == 'cold':
        demoted_warm += 1

if any([demoted_hot, promoted_warm, demoted_warm]):
    log(f"Exchange: {demoted_hot} hot→warm, {promoted_warm} warm→hot, {demoted_warm} warm→cold")
log(f"Warm saturation: {warm_saturation}% {'(Cold eviction suppressed)' if warm_saturation < WARM_SATURATION else ''}")

# title_only 判定
for e in merged_entries:
    if e['tier'] in ('hot', 'warm'):
        e['title_only'] = False
    else:
        etype = e.get('type', 'knowledge')
        hits = e.get('hit_count', 1)
        if etype in FULL_TYPES:
            e['title_only'] = False
        elif etype in TITLE_TYPES:
            e['title_only'] = True
        else:
            e['title_only'] = hits < 3

# ═══════════════════════════════════════════════════════════════
#  Step 4: Cold detail → SQLite 存储 (替代 full_detail.json)
# ═══════════════════════════════════════════════════════════════

cold_detail_written = 0
conn = None
try:
    conn = sqlite3.connect(FTS_DB)
    c = conn.cursor()
    # 确保 memories 表存在 (如果 FTS5 还未建)
    c.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            timestamp TEXT, type TEXT, summary TEXT,
            detail TEXT DEFAULT '', tags TEXT DEFAULT '',
            fingerprint TEXT DEFAULT '', hit_count INTEGER DEFAULT 1,
            score REAL DEFAULT 0, tier TEXT DEFAULT 'warm',
            importance INTEGER DEFAULT 5,
            author TEXT DEFAULT '', contributors TEXT DEFAULT '',
            date TEXT
        )
    ''')

    for e in merged_entries:
        detail = e.get('detail', '')
        is_cold_title = (e['tier'] == 'cold' and e.get('title_only'))

        if is_cold_title and detail:
            # 写 detail 到 SQLite
            c.execute('''
                INSERT OR REPLACE INTO memories
                (id, timestamp, type, summary, detail, tags, fingerprint,
                 hit_count, score, tier, importance, author, contributors, date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                e.get('id', ''),
                e.get('timestamp', ''),
                e.get('type', 'knowledge'),
                e.get('summary', ''),
                detail,  # 完整 detail 存入 SQLite
                ','.join(e.get('tags', []) or []),
                e.get('fingerprint', ''),
                e.get('hit_count', 1),
                e.get('score', 0),
                e['tier'],
                e.get('importance', 5),
                e.get('author', ''),
                '',
                e.get('timestamp', '')[:10] if e.get('timestamp') else ''
            ))
            cold_detail_written += 1
            # Cold title_only → 从 consolidated 中移除 detail
            e['detail'] = ''
            e['source_raw'] = e.get('_source', f'auto/{e.get("id","unknown")}')

        elif is_cold_title:
            # 没有 detail 的 cold → 只设 source 指针
            e['source_raw'] = e.get('_source', f'auto/{e.get("id","unknown")}')

    if cold_detail_written:
        conn.commit()

finally:
    if conn:
        conn.close()

if cold_detail_written:
    log(f"Cold detail stored in SQLite: {cold_detail_written} entries")

# 清理内部字段
for e in merged_entries:
    e.pop('_source', None)

# ═══════════════════════════════════════════════════════════════
#  Step 5: Write consolidated.json
# ═══════════════════════════════════════════════════════════════

hot_list = [e for e in merged_entries if e['tier'] == 'hot']
warm_list = [e for e in merged_entries if e['tier'] == 'warm']
cold_list = [e for e in merged_entries if e['tier'] == 'cold']
title_only_count = sum(1 for e in merged_entries if e.get('title_only'))

output = {
    "schema_version": "4.2",
    "type": "consolidated",
    "priority": 1,
    "created": datetime.now(timezone.utc).isoformat(),
    "total_raw_entries": source_stats['raw'],
    "total_consolidated": len(merged_entries),
    "scoring": f"Score = I × e^(-λt) × log(f+1), half_life={HALF_LIFE_DAYS}days",
    "tier_summary": {
        "hot": len(hot_list),
        "warm": len(warm_list),
        "cold": len(cold_list),
        "title_only": title_only_count,
        "warm_saturation_pct": warm_saturation,
    },
    "exchange": {
        "hot_to_warm": demoted_hot,
        "warm_to_hot": promoted_warm,
        "warm_to_cold": demoted_warm,
    },
    "entries": merged_entries
}

save_json(CURATED_FILE, output)
log(f"Tiers: Hot={len(hot_list)} Warm={len(warm_list)} Cold={len(cold_list)} (title_only={title_only_count})")

# ═══════════════════════════════════════════════════════════════
#  Step 6: Refresh cache
# ═══════════════════════════════════════════════════════════════

cache = {
    "schema_version": "4.2",
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "hot_tier": {
        "count": len(hot_list),
        "max": HOT_CAP,
        "entries": [{
            "id": e.get("id","") or e.get("fingerprint","")[:20],
            "type": e.get("type","knowledge"),
            "summary": e["summary"],
            "score": e["score"],
            "importance": e.get("importance", 5),
            "hit_count": e["hit_count"],
            "last_hit": e.get("last_hit", ""),
            "tags": e.get("tags", [])
        } for e in hot_list]
    },
    "warm_tier": {"count": len(warm_list)},
    "cold_tier": {"count": len(cold_list)},
    "stats": output["tier_summary"]
}
save_json(CACHE_FILE, cache)

# ═══════════════════════════════════════════════════════════════
#  Report & FTS rebuild
# ═══════════════════════════════════════════════════════════════

log("=== Compress Complete ===")
ts = output['tier_summary']
log(f"  Hot: {ts['hot']}  Warm: {ts['warm']}  Cold: {ts['cold']}  (title_only: {ts['title_only']})")
log(f"  Exchange: {demoted_hot}→warm {promoted_warm}→hot {demoted_warm}→cold")

try:
    open(LOCK_FILE, 'w').close()
except:
    pass

fts_script = os.path.join(os.path.dirname(__file__), 'rebuild_fts.py')
if os.path.exists(fts_script):
    log("Rebuilding FTS5 search index...")
    result = subprocess.run([sys.executable, fts_script], capture_output=True, text=True)
    for line in result.stdout.strip().split('\n'):
        if line.strip():
            log(f"  {line.strip()}")
    if result.returncode != 0:
        log(f"  FTS error: {result.stderr.strip()}")

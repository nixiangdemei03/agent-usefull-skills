#!/usr/bin/env python3
"""EMS v2 — Tier Summary Printer
Called by consolidate.sh. Takes auto_dir as argument."""
import json, os, sys

auto_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'auto')
hot = warm = cold = archive = total = 0

if os.path.isdir(auto_dir):
    for f in sorted(os.listdir(auto_dir)):
        if not f.endswith('.json'):
            continue
        with open(os.path.join(auto_dir, f)) as fh:
            try:
                entries = json.load(fh)
            except:
                continue
        for e in entries:
            t = e.get('tier', 'warm')
            if t == 'hot':
                hot += 1
            elif t == 'warm':
                warm += 1
            elif t == 'cold':
                cold += 1
            else:
                archive += 1
        total += len(entries)

print(f'hot={hot} warm={warm} cold={cold} archive={archive} total={total}')

#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform/lineshine'))
from launch_numa import make_groups
for domains in (1,2,4,8,16):
    groups=make_groups(32*domains,1,domains)
    assert len(groups)==32*domains
    assert set(c//38 for g in groups for c in g)==set(range(domains))
    assert all(c%38<32 for g in groups for c in g)
groups=make_groups(592,1,16)
assert len({c for g in groups for c in g})==592
assert all(c%38!=37 for g in groups for c in g)
for args in [(608,1,16),(64,1,1),(32,1,3),(33,1,2),(16,38,16)]:
    try: make_groups(*args)
    except ValueError: pass
    else: raise AssertionError(args)
print('PASS: prefix NUMA mapping, uniqueness, system-core exclusion and invalid layouts')

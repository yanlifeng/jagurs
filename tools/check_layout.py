#!/usr/bin/env python3
"""Assert the deliberately small change boundary against the frozen Git base."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = 'fddf60996db9044d1bedb18d8d281dd8804e2bf8'


def original(name):
    return subprocess.check_output(['git', 'show', BASE+':'+name], cwd=ROOT)


def main():
    files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE], cwd=ROOT, text=True).splitlines()
    checked = 0
    for name in files:
        if name.startswith('src/'):
            if name in ('src/JAGURS.f90', 'src/mod_onefile.f90'):
                continue
            if Path(name).name.startswith('Makefile'):
                if (ROOT/name).is_symlink():
                    assert str((ROOT/name).readlink()).encode() == original(name), name
                else:
                    new = (ROOT/name).read_bytes()
                    restored = new.replace(b'mod_coupling_output.o JAGURS.o', b'JAGURS.o')
                    restored = restored.replace(b'mod_coupling_output.obj JAGURS.obj', b'JAGURS.obj')
                    assert restored == original(name), 'Non-mechanical build change: '+name
                continue
        elif not name.startswith('benchmarks/'):
            continue
        assert (ROOT/name).read_bytes() == original(name), 'Protected file changed: '+name
        checked += 1
    # The CPU optimization was previously validated as opt01. Preserve it
    # byte-for-byte when moving it out of the LineShine experiment directory.
    expected = '3c2b77aaf620f8be76980f40670b6bf3b658d3e2c2dabc96e18d8cbef16da137'
    actual = hashlib.sha256((ROOT/'src/mod_onefile.f90').read_bytes()).hexdigest()
    assert actual == expected, 'Common collective path changed beyond relocation'
    print(json.dumps(dict(passed=True, protected_files=checked,
                          collective_source_sha256=actual, base=BASE), indent=2))


if __name__ == '__main__':
    main()

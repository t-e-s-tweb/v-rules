#!/usr/bin/env python3
"""
Fix: allow CUSTOM profiles with unknown protocols (masque, tuic, ...)
through the policy-group and proxy-chain member filters.

The server-address filters there assume the profile has a resolvable
`server` field. CUSTOM profiles may not (their proxy outbound can keep
the address in a protocol-specific place). Skip the filters for CUSTOM.
Idempotent.
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path("V2rayNG")
p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"

if not p.exists():
    print(f"✗ {p} not found")
    sys.exit(1)

c = p.read_text(encoding="utf-8")

if "it.configType == EConfigType.CUSTOM ||\n                            it.server.isNotNullEmpty()" in c \
        or "it.configType == EConfigType.CUSTOM || it.server.isNotNullEmpty()" in c:
    print("• already patched")
    sys.exit(0)

# Match the two consecutive filters in either pristine or single-line form.
pat = re.compile(
    r'(?P<indent>[ \t]*)\.filter\s*\{\s*it\.server\.isNotNullEmpty\(\)\s*\}\s*\n'
    r'(?P=indent)\.filter\s*\{\s*Utils\.isPureIpAddress\(it\.server!!\)\s*\|\|\s*'
    r'Utils\.isValidUrl\(it\.server!!\)\s*\}'
)

def repl(m):
    indent = m.group("indent")
    return (
        f'{indent}.filter {{\n'
        f'{indent}    it.configType == EConfigType.CUSTOM ||\n'
        f'{indent}            it.server.isNotNullEmpty()\n'
        f'{indent}}}\n'
        f'{indent}.filter {{\n'
        f'{indent}    it.configType == EConfigType.CUSTOM ||\n'
        f'{indent}            Utils.isPureIpAddress(it.server!!) ||\n'
        f'{indent}            Utils.isValidUrl(it.server!!)\n'
        f'{indent}}}'
    )

c2, n = pat.subn(repl, c)

if n == 0:
    print("⚠ filters not matched — inspect CoreConfigContextBuilder.kt manually")
    sys.exit(1)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(p, p.with_suffix(f".kt.bak.{ts}"))
p.write_text(c2, encoding="utf-8")
print(f"✓ patched {n} filter pair(s) (policy group + proxy chain)")

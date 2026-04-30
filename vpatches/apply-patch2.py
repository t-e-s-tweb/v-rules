#!/usr/bin/env python3
"""Robust fix: replace resolveCurrentServer body using regex."""

import re
from pathlib import Path

target = Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt")
content = target.read_text(encoding="utf-8")

# Pattern to match the entire function, capturing indentation
pattern = re.compile(
    r'(?P<indent>[ \t]*)private fun resolveCurrentServer\(remark: String\?\): String\? \{\s*\n'
    r'(?P<body>.*?)\n'
    r'(?P=indent)\}',
    re.DOTALL
)

def new_body(indent):
    return (
        f'{indent}private fun resolveCurrentServer(remark: String?): String? {{\n'
        f'{indent}    if (remark == AppConfig.CURRENT_SERVER) {{\n'
        f'{indent}        val currId = MmkvManager.getSelectServer()\n'
        f'{indent}        if (!currId.isNullOrEmpty()) {{\n'
        f'{indent}            val profile = MmkvManager.decodeServerConfig(currId)\n'
        f'{indent}            return profile?.remarks\n'
        f'{indent}        }}\n'
        f'{indent}    }}\n'
        f'{indent}    return remark\n'
        f'{indent}}}'
    )

match = pattern.search(content)
if match:
    indent = match.group('indent')
    content = content[:match.start()] + new_body(indent) + content[match.end():]
    target.write_text(content, encoding="utf-8")
    print("✅ resolveCurrentServer replaced successfully.")
else:
    # Fallback: if not found, maybe not added yet? Let user know.
    print("⚠️ Could not find resolveCurrentServer function. It may not exist yet.")
    print("   Try running the spinner patcher first, then this fix.")

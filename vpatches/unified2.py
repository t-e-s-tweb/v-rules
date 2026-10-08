#!/usr/bin/env python3
"""
Fix: make V2rayConfig.getProxyOutbound() recognise protocols the app's
EConfigType enum does not know about (masque, tuic, ...). Same treatment
for getAllProxyOutbound(). Idempotent.
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path("V2rayNG")
p = BASE / "app/src/main/java/com/v2ray/ang/dto/V2rayConfig.kt"

if not p.exists():
    print(f"✗ {p} not found")
    sys.exit(1)

c = p.read_text(encoding="utf-8")

# Idempotency marker
if "builtinNonProxy" in c:
    print("• V2rayConfig: already patched")
    sys.exit(0)

changed = False

# ---- getProxyOutbound ----
old_proxy = '''    fun getProxyOutbound(): OutboundBean? {
        outbounds.forEach { outbound ->
            EConfigType.entries.forEach {
                if (outbound.protocol.equals(it.name, true)) {
                    return outbound
                }
            }
        }
        return null
    }'''
new_proxy = '''    fun getProxyOutbound(): OutboundBean? {
        // Prefer the outbound explicitly tagged "proxy"; that is the
        // convention used by the app templates and v2rayN exports.
        outbounds.firstOrNull { it.tag == AppConfig.TAG_PROXY }?.let { return it }
        // Otherwise fall back to the first outbound that is not one of the
        // core's built-in non-proxy protocols. This lets protocols the app
        // does not know about (masque, tuic, ...) still be picked up when
        // they appear in a custom config.
        val builtinNonProxy = setOf("freedom", "blackhole", "dns")
        return outbounds.firstOrNull { outbound ->
            !builtinNonProxy.contains(outbound.protocol.lowercase())
        }
    }'''
if old_proxy in c:
    c = c.replace(old_proxy, new_proxy, 1)
    changed = True
    print("✓ V2rayConfig: rewrote getProxyOutbound()")
elif "outbounds.firstOrNull { it.tag == AppConfig.TAG_PROXY }" in c:
    print("• V2rayConfig: getProxyOutbound already rewritten")
else:
    print("⚠ V2rayConfig: getProxyOutbound not matched")

# ---- getAllProxyOutbound ----
old_all = '''    fun getAllProxyOutbound(): List<OutboundBean> {
        return outbounds.filter { outbound ->
            EConfigType.entries.any { it.name.equals(outbound.protocol, ignoreCase = true) }
        }
    }'''
new_all = '''    fun getAllProxyOutbound(): List<OutboundBean> {
        // Any outbound that is not one of the core's built-in non-proxy
        // protocols is treated as a proxy outbound. This keeps the app
        // agnostic to protocol names it does not model in EConfigType.
        val builtinNonProxy = setOf("freedom", "blackhole", "dns")
        return outbounds.filter { outbound ->
            !builtinNonProxy.contains(outbound.protocol.lowercase())
        }
    }'''
if old_all in c:
    c = c.replace(old_all, new_all, 1)
    changed = True
    print("✓ V2rayConfig: rewrote getAllProxyOutbound()")
elif "builtinNonProxy.contains(outbound.protocol.lowercase())" in c and "getAllProxyOutbound" in c:
    print("• V2rayConfig: getAllProxyOutbound already rewritten")
else:
    print("⚠ V2rayConfig: getAllProxyOutbound not matched")

if changed:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(p, p.with_suffix(f".kt.bak.{ts}"))
    p.write_text(c, encoding="utf-8")
    print("✓ written")
else:
    print("• nothing to write")

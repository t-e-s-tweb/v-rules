#!/usr/bin/env python3
"""
Unified patcher: makes both getMoreOutbounds and applySubscriptionChain
reuse the existing 'proxy' outbound when the front/landing proxy resolves
to the currently active server.

Run this AFTER the spinner patch and resolveCurrentServer fix.
"""

import re
from pathlib import Path

TARGET = Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt")

def apply():
    content = TARGET.read_text(encoding="utf-8")
    original = content

    # ── 1. getMoreOutbounds signature ─────────────────────────────────
    content = content.replace(
        "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String): Boolean {",
        "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String, mainProfileRemarks: String? = null): Boolean {"
    )

    # ── 2. Call sites (normal + speedtest) ────────────────────────────
    for old in ["getMoreOutbounds(v2rayConfig, config.subscriptionId)"]:
        new = "getMoreOutbounds(v2rayConfig, config.subscriptionId, config.remarks)"
        content = content.replace(old, new)

    # ── 3. Previous proxy block ──────────────────────────────────────
    old_prev = (
        "            //Previous proxy\n"
        "            val prevNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.prevProfile) ?: subItem.prevProfile)\n"
        "            if (prevNode != null) {\n"
        "                val prevOutbound = convertProfile2Outbound(prevNode)\n"
        "                if (prevOutbound != null) {\n"
        "                    updateOutboundWithGlobalSettings(prevOutbound)\n"
        '                    prevOutbound.tag = AppConfig.TAG_PROXY + "2"\n'
        "                    v2rayConfig.outbounds.add(prevOutbound)\n"
        "                    outbound.ensureSockopt().dialerProxy = prevOutbound.tag\n"
        "                }\n"
        "            }"
    )
    new_prev = (
        "            //Previous proxy\n"
        "            val prevNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.prevProfile) ?: subItem.prevProfile)\n"
        "            if (prevNode != null) {\n"
        "                if (prevNode.remarks == mainProfileRemarks) {\n"
        "                    // Same as main server – reuse existing 'proxy' outbound\n"
        "                    outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY\n"
        '                    LogUtil.d(AppConfig.TAG, "Prev proxy is main server, set dialerProxy to proxy")\n'
        "                } else {\n"
        "                    val prevOutbound = convertProfile2Outbound(prevNode)\n"
        "                    if (prevOutbound != null) {\n"
        "                        updateOutboundWithGlobalSettings(prevOutbound)\n"
        '                        prevOutbound.tag = AppConfig.TAG_PROXY + "2"\n'
        "                        v2rayConfig.outbounds.add(prevOutbound)\n"
        "                        outbound.ensureSockopt().dialerProxy = prevOutbound.tag\n"
        "                    }\n"
        "                }\n"
        "            }"
    )
    if old_prev in content:
        content = content.replace(old_prev, new_prev)
        print("✓ Patched prev proxy block")
    else:
        print("✗ Could not find prev proxy block – ensure spinner patch is applied first")
        return False

    # ── 4. Next proxy block ──────────────────────────────────────────
    old_next = (
        "            //Next proxy\n"
        "            val nextNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.nextProfile) ?: subItem.nextProfile)\n"
        "            if (nextNode != null) {\n"
        "                val nextOutbound = convertProfile2Outbound(nextNode)\n"
        "                if (nextOutbound != null) {\n"
        "                    updateOutboundWithGlobalSettings(nextOutbound)\n"
        "                    nextOutbound.tag = AppConfig.TAG_PROXY\n"
        "                    v2rayConfig.outbounds.add(0, nextOutbound)\n"
        '                    outbound.tag = AppConfig.TAG_PROXY + "1"\n'
        "                    nextOutbound.ensureSockopt().dialerProxy = outbound.tag\n"
        "                }\n"
        "            }"
    )
    new_next = (
        "            //Next proxy\n"
        "            val nextNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.nextProfile) ?: subItem.nextProfile)\n"
        "            if (nextNode != null) {\n"
        "                if (nextNode.remarks == mainProfileRemarks) {\n"
        "                    // Same as main server – nothing to add\n"
        '                    LogUtil.d(AppConfig.TAG, "Next proxy is main server, skipping")\n'
        "                } else {\n"
        "                    val nextOutbound = convertProfile2Outbound(nextNode)\n"
        "                    if (nextOutbound != null) {\n"
        "                        updateOutboundWithGlobalSettings(nextOutbound)\n"
        "                        nextOutbound.tag = AppConfig.TAG_PROXY\n"
        "                        v2rayConfig.outbounds.add(0, nextOutbound)\n"
        '                        outbound.tag = AppConfig.TAG_PROXY + "1"\n'
        "                        nextOutbound.ensureSockopt().dialerProxy = outbound.tag\n"
        "                    }\n"
        "                }\n"
        "            }"
    )
    if old_next in content:
        content = content.replace(old_next, new_next)
        print("✓ Patched next proxy block")
    else:
        print("✗ Could not find next proxy block – ensure spinner patch is applied first")
        return False

    # ── 5. applySubscriptionChain (if present) ───────────────────────
    if "private fun applySubscriptionChain" in content:
        # Attempt to find the chainProfile line and insert the reuse logic
        pattern = re.compile(
            r'(?P<indent>[ \t]*)val chainProfile = SettingsManager\.getServerViaRemarks\(.*?\n'
        )
        match = re.search(pattern, content)
        if match:
            line_indent = match.group('indent')
            insertion = (
                f"{line_indent}// If the chain profile is the same as the current main server, reuse existing proxy outbound\n"
                f"{line_indent}val mainRemarks = MmkvManager.getSelectServer()?.let {{ MmkvManager.decodeServerConfig(it)?.remarks }}\n"
                f"{line_indent}if (chainProfile.remarks == mainRemarks) {{\n"
                f"{line_indent}    outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY\n"
                f'{line_indent}    LogUtil.d(AppConfig.TAG, "Chain proxy is main server, set dialerProxy to proxy")\n'
                f"{line_indent}    return\n"
                f"{line_indent}}}\n"
            )
            insert_pos = match.end()
            content = content[:insert_pos] + insertion + content[insert_pos:]
            print("✓ Inserted reuse check into applySubscriptionChain")
        else:
            print("⚠ applySubscriptionChain found but 'chainProfile' line not located – skipping")
    else:
        print("ℹ applySubscriptionChain not present (custom chain patch not applied) – nothing to do")

    # Write back if any changes were made
    if content != original:
        TARGET.write_text(content, encoding="utf-8")
        print("\n✅ Reuse proxy logic applied successfully.")
        print("👉 Rebuild the app and test.")
    else:
        print("\n⚠ No changes made – file may already be patched or missing expected blocks.")

if __name__ == "__main__":
    apply()

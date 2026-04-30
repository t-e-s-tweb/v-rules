#!/usr/bin/env python3
"""
When front/landing proxy equals the main active server, reuse the existing 'proxy'
outbound instead of creating a duplicate. Sets dialerProxy = "proxy" and skips
adding a new outbound.

Works with the CURRENT state of V2rayConfigManager.kt (including previous patches).
"""

import re
from pathlib import Path

target = Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt")
content = target.read_text(encoding="utf-8")

# ------------------------------------------------------------------
# 1. Update getMoreOutbounds signature (if not already)
# ------------------------------------------------------------------
old_sig = "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String): Boolean {"
new_sig = "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String, mainProfileRemarks: String? = null): Boolean {"
if old_sig in content:
    content = content.replace(old_sig, new_sig)
    print("✓ Updated getMoreOutbounds signature")

# ------------------------------------------------------------------
# 2. Previous proxy block – capture entire //Previous proxy ... block
# ------------------------------------------------------------------
prev_pattern = re.compile(
    r'(?P<indent>[ \t]*)//Previous proxy\s*\n'
    r'(?P<block>(?P=indent)\s+val prevNode = SettingsManager\.getServerViaRemarks.*?\n'
    r'(?:.*?\n)*?'
    r'(?P=indent)\s+\})',
    re.MULTILINE
)
def replace_prev(match):
    indent = match.group('indent')
    new = f"""{indent}//Previous proxy
{indent}val prevNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.prevProfile) ?: subItem.prevProfile)
{indent}if (prevNode != null) {{
{indent}    if (prevNode.remarks == mainProfileRemarks) {{
{indent}        // Same as main server – reuse existing 'proxy' outbound
{indent}        outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
{indent}        LogUtil.d(AppConfig.TAG, "Prev proxy is the same as main server, set dialerProxy to proxy")
{indent}    }} else {{
{indent}        val prevOutbound = convertProfile2Outbound(prevNode)
{indent}        if (prevOutbound != null) {{
{indent}            updateOutboundWithGlobalSettings(prevOutbound)
{indent}            prevOutbound.tag = AppConfig.TAG_PROXY + "2"
{indent}            v2rayConfig.outbounds.add(prevOutbound)
{indent}            outbound.ensureSockopt().dialerProxy = prevOutbound.tag
{indent}        }}
{indent}    }}
{indent}}}"""
    return new

content = prev_pattern.sub(replace_prev, content)
print("✓ Updated prev proxy block")

# ------------------------------------------------------------------
# 3. Next proxy block – capture entire //Next proxy ... block
# ------------------------------------------------------------------
next_pattern = re.compile(
    r'(?P<indent>[ \t]*)//Next proxy\s*\n'
    r'(?P<block>(?P=indent)\s+val nextNode = SettingsManager\.getServerViaRemarks.*?\n'
    r'(?:.*?\n)*?'
    r'(?P=indent)\s+\})',
    re.MULTILINE
)
def replace_next(match):
    indent = match.group('indent')
    new = f"""{indent}//Next proxy
{indent}val nextNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.nextProfile) ?: subItem.nextProfile)
{indent}if (nextNode != null) {{
{indent}    if (nextNode.remarks == mainProfileRemarks) {{
{indent}        // Same as main server – nothing to do, main outbound already acts as entry
{indent}        LogUtil.d(AppConfig.TAG, "Next proxy is the same as main server, skipping")
{indent}    }} else {{
{indent}        val nextOutbound = convertProfile2Outbound(nextNode)
{indent}        if (nextOutbound != null) {{
{indent}            updateOutboundWithGlobalSettings(nextOutbound)
{indent}            nextOutbound.tag = AppConfig.TAG_PROXY
{indent}            v2rayConfig.outbounds.add(0, nextOutbound)
{indent}            outbound.tag = AppConfig.TAG_PROXY + "1"
{indent}            nextOutbound.ensureSockopt().dialerProxy = outbound.tag
{indent}        }}
{indent}    }}
{indent}}}"""
    return new

content = next_pattern.sub(replace_next, content)
print("✓ Updated next proxy block")

# ------------------------------------------------------------------
# 4. Update call sites to pass mainProfileRemarks = config.remarks
# ------------------------------------------------------------------
old_call = "getMoreOutbounds(v2rayConfig, config.subscriptionId)"
new_call = "getMoreOutbounds(v2rayConfig, config.subscriptionId, config.remarks)"
# Replace all occurrences, but only if not already containing the parameter
content = content.replace(old_call, new_call)
print("✓ Updated call sites")

# ------------------------------------------------------------------
# 5. applySubscriptionChain – add check for same main server
# ------------------------------------------------------------------
# We need to locate the line: val chainProfile = SettingsManager.getServerViaRemarks(...)
# Then insert the check right after it.
chain_pattern = re.compile(
    r'(?P<indent>[ \t]*)val chainProfile = SettingsManager\.getServerViaRemarks\(.*?\n'
    r'(?P<rest>(?P=indent)\s+\S.*?\n)?'  # optional next line (e.g. "val")
)
# Better: use a regex that finds the exact line and inserts after it.
lines = content.splitlines(True)
output_lines = []
inside_chain_fun = False
for line in lines:
    output_lines.append(line)
    if "val chainProfile = SettingsManager.getServerViaRemarks" in line:
        # Get indentation
        indent = line[:len(line) - len(line.lstrip())]
        output_lines.append(f"{indent}// If chain profile is the same as the main active server, reuse existing proxy\n")
        output_lines.append(f"{indent}val mainRemarks = MmkvManager.getSelectServer()?.let {{ MmkvManager.decodeServerConfig(it)?.remarks }}\n")
        output_lines.append(f"{indent}if (chainProfile.remarks == mainRemarks) {{\n")
        output_lines.append(f"{indent}    outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY\n")
        output_lines.append(f"{indent}    LogUtil.d(AppConfig.TAG, \"Chain proxy is the main server, set dialerProxy to proxy\")\n")
        output_lines.append(f"{indent}    return\n")
        output_lines.append(f"{indent}}}\n")
        print("✓ Inserted main server check in applySubscriptionChain")
        # After insertion, we need to skip the original following line(s) that were already part of the block.
        # Actually, the check is added after the line, so the next lines (which are part of the chain creation) remain.
        # This is correct.
content = ''.join(output_lines)

target.write_text(content, encoding="utf-8")
print("\n✅ All modifications applied. Rebuild and test.")

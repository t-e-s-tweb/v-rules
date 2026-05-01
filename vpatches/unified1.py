#!/usr/bin/env python3
"""Fix: resolve CURRENT_SERVER before passing to addChainOutbound in applySubscriptionChain."""

from pathlib import Path

target = Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt")
content = target.read_text(encoding="utf-8")

# Old call (prev)
old_prev_call = "addChainOutbound(subItem.prevProfile, \"prev\", \"$originalTag-prev\")"
new_prev_call = "addChainOutbound(resolveCurrentServer(subItem.prevProfile), \"prev\", \"$originalTag-prev\")"

# Old call (next)
old_next_call = "addChainOutbound(subItem.nextProfile, \"next\", originalTag)"
new_next_call = "addChainOutbound(resolveCurrentServer(subItem.nextProfile), \"next\", originalTag)"

if old_prev_call in content:
    content = content.replace(old_prev_call, new_prev_call)
    print("✓ Resolved prevProfile before chain call")
else:
    print("✗ Could not find prev call in applySubscriptionChain")

if old_next_call in content:
    content = content.replace(old_next_call, new_next_call)
    print("✓ Resolved nextProfile before chain call")
else:
    print("✗ Could not find next call in applySubscriptionChain")

target.write_text(content, encoding="utf-8")
print("Done. Rebuild and test – dialerProxy will now be set for Current Server front proxy.")

#!/usr/bin/env python3
"""
Patches V2rayConfigManager.kt with subscription chaining (prev/next).
- Clean tag names: prev = tag-prev, next takes over original tag, original becomes tag-orig.
- Next proxy appended (not inserted at 0) like previous proxy.
- Deduplication prevents duplicate outbounds.
"""

import re
import sys
import shutil
from datetime import datetime
from pathlib import Path


def create_backup(filepath: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = filepath.with_suffix(f".kts.bak.{timestamp}")
    shutil.copy2(filepath, backup)
    print(f"Backup: {backup}")
    return backup


def patch_file(filepath: Path) -> bool:
    print(f"Patching: {filepath}")
    content = filepath.read_text(encoding="utf-8")

    # --- 1. Modify injectCustomOutbounds signature ---
    old_sig = "private fun injectCustomOutbounds(v2rayConfig: V2rayConfig) {"
    new_sig = "private fun injectCustomOutbounds(v2rayConfig: V2rayConfig, outboundTagMap: MutableMap<String, String> = mutableMapOf()) {"
    if old_sig in content:
        content = content.replace(old_sig, new_sig)
        print("  ✓ Updated injectCustomOutbounds signature")
    else:
        print("  ✗ Could not find injectCustomOutbounds signature")
        return False

    # --- 2. Replace tag assignment block ---
    pattern = re.compile(
        r'(\s*)updateOutboundWithGlobalSettings\(outbound\)\s*\n'
        r'\s*outbound\.tag = tag\s*\n'
        r'\s*v2rayConfig\.outbounds\.add\(outbound\)\s*\n'
        r'\s*existingTags\.add\(tag\)\s*\n'
        r'\s*LogUtil\.d\(AppConfig\.TAG, "Injected custom outbound: tag=\'\$tag\'"\)'
    )
    match = pattern.search(content)
    if not match:
        print("  ✗ Could not find outbound tag assignment block")
        return False

    indent = match.group(1)
    new_block = f'''{indent}updateOutboundWithGlobalSettings(outbound)
{indent}
{indent}// Deduplication: skip if this custom outbound has already been injected
{indent}if (outboundTagMap.containsKey(tag)) {{
{indent}    LogUtil.d(AppConfig.TAG, "Custom outbound '$tag' already injected, skipping")
{indent}    return@forEach
{indent}}}
{indent}outbound.tag = tag
{indent}
{indent}// Apply subscription chain (prev/next proxy) if applicable
{indent}applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)
{indent}
{indent}v2rayConfig.outbounds.add(outbound)
{indent}existingTags.add(tag)
{indent}outboundTagMap[tag] = tag
{indent}LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$tag'")'''
    content = content[:match.start()] + new_block + content[match.end():]
    print("  ✓ Replaced outbound tag assignment block")

    # --- 3. Insert applySubscriptionChain function (next appended) ---
    routing_pattern = re.compile(r'(\n\s*private fun getRouting\([^)]*\):)')
    match = re.search(routing_pattern, content)
    if not match:
        print("  ✗ Could not find getRouting function")
        return False

    new_function = '''
    /**
     * Applies subscription chain (previous/next proxy) to an injected custom outbound.
     * - Prev outbound gets tag "$originalTag-prev"
     * - Next outbound takes over originalTag; original is renamed "$originalTag-orig"
     * - Both chain outbounds are appended (not inserted at 0)
     * - Deduplication prevents duplicates.
     */
    private fun applySubscriptionChain(
        v2rayConfig: V2rayConfig,
        profile: ProfileItem,
        outbound: V2rayConfig.OutboundBean,
        outboundTagMap: MutableMap<String, String>,
        existingTags: MutableSet<String>
    ) {
        if (profile.subscriptionId.isNullOrEmpty()) return
        
        val subItem = MmkvManager.decodeSubscription(profile.subscriptionId) ?: return
        val originalTag = outbound.tag
        
        fun addChainOutbound(
            targetRemark: String?,
            chainType: String,
            desiredTag: String,
            chainTo: (V2rayConfig.OutboundBean) -> Unit
        ) {
            if (targetRemark.isNullOrEmpty()) return
            
            // 1. Check if an outbound with the desired tag already exists
            val existingByTag = v2rayConfig.outbounds.firstOrNull { it.tag == desiredTag }
            if (existingByTag != null) {
                chainTo(existingByTag)
                outboundTagMap["$chainType-$targetRemark"] = desiredTag
                LogUtil.d(AppConfig.TAG, "Reused existing $chainType outbound: $desiredTag")
                return
            }
            
            // 2. Check deduplication map
            val mapKey = "$chainType-$targetRemark"
            val existingTag = outboundTagMap[mapKey]
            if (existingTag != null) {
                val existingOutbound = v2rayConfig.outbounds.firstOrNull { it.tag == existingTag }
                if (existingOutbound != null) {
                    chainTo(existingOutbound)
                    LogUtil.d(AppConfig.TAG, "Reused $chainType outbound (map): $existingTag")
                    return
                }
            }
            
            // 3. Create new outbound
            val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return
            val chainOutbound = convertProfile2Outbound(chainProfile) ?: return
            updateOutboundWithGlobalSettings(chainOutbound)
            chainOutbound.tag = desiredTag
            outboundTagMap[mapKey] = desiredTag
            
            chainTo(chainOutbound)
            v2rayConfig.outbounds.add(chainOutbound)  // APPEND, not insert at 0
            existingTags.add(desiredTag)
            LogUtil.d(AppConfig.TAG, "Created $chainType outbound: $desiredTag")
        }
        
        // Previous proxy
        addChainOutbound(subItem.prevProfile, "prev", "$originalTag-prev") { prevOutbound ->
            outbound.ensureSockopt().dialerProxy = prevOutbound.tag
        }
        
        // Next proxy (takes over original tag, original renamed)
        if (!subItem.nextProfile.isNullOrEmpty()) {
            val newOriginalTag = "$originalTag-orig"
            outbound.tag = newOriginalTag
            
            addChainOutbound(subItem.nextProfile, "next", originalTag) { nextOutbound ->
                nextOutbound.ensureSockopt().dialerProxy = newOriginalTag
                // nextOutbound is already appended via addChainOutbound's add()
            }
        }
    }
'''
    content = content[:match.start()] + new_function + "\n" + content[match.start():]
    print("  ✓ Inserted applySubscriptionChain function (next appended)")

    # --- 4. Modify getRouting call ---
    old_call = "            injectCustomOutbounds(v2rayConfig)"
    new_call = '''            val outboundTagMap = mutableMapOf<String, String>()
            injectCustomOutbounds(v2rayConfig, outboundTagMap)'''
    if old_call in content:
        content = content.replace(old_call, new_call)
        print("  ✓ Updated getRouting call")
    else:
        print("  ✗ Could not find injectCustomOutbounds call in getRouting")
        return False

    filepath.write_text(content, encoding="utf-8")
    print("  ✅ Patch applied successfully.")
    return True


def main():
    if len(sys.argv) < 2:
        target = Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt")
    else:
        target = Path(sys.argv[1])
    if not target.exists():
        print(f"File not found: {target}")
        sys.exit(1)
    create_backup(target)
    if patch_file(target):
        print("\n👉 Rebuild and test. Both prev and next proxies are now appended.")
    else:
        print("\n❌ Patching failed. Restore from backup.")


if __name__ == "__main__":
    main()

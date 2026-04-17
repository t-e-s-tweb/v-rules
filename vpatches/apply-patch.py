#!/usr/bin/env python3
"""
Patches V2rayConfigManager.kt with subscription chaining + deduplication.
No fake imports – uses existing ensureSockopt extension.
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

    # --- 2. Replace tag assignment block using regex (flexible whitespace) ---
    pattern = re.compile(
        r'(\s*)updateOutboundWithGlobalSettings\(outbound\)\s*\n'
        r'\s*outbound\.tag = tag\s*\n'
        r'\s*v2rayConfig\.outbounds\.add\(outbound\)\s*\n'
        r'\s*existingTags\.add\(tag\)\s*\n'
        r'\s*LogUtil\.d\(AppConfig\.TAG, "Injected custom outbound: tag=\'\$tag\'"\)'
    )
    match = pattern.search(content)
    if not match:
        print("  ✗ Could not find outbound tag assignment block (regex)")
        return False

    indent = match.group(1)
    new_block = f'''{indent}updateOutboundWithGlobalSettings(outbound)
{indent}
{indent}// Generate unique tag for deduplication tracking
{indent}val injectedTag = if (tag in outboundTagMap) {{
{indent}    outboundTagMap[tag]!!
{indent}}} else {{
{indent}    val newTag = "custom-${{tag.hashCode().toString(16).take(8)}}"
{indent}    outboundTagMap[tag] = newTag
{indent}    newTag
{indent}}}
{indent}outbound.tag = injectedTag
{indent}
{indent}// Apply subscription chain (prev/next proxy) if applicable
{indent}applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)
{indent}
{indent}v2rayConfig.outbounds.add(outbound)
{indent}existingTags.add(injectedTag)
{indent}LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$injectedTag', original='$tag'")'''
    
    content = content[:match.start()] + new_block + content[match.end():]
    print("  ✓ Replaced outbound tag assignment block")

    # --- 3. Insert applySubscriptionChain function before getRouting ---
    routing_pattern = re.compile(r'(\n\s*private fun getRouting\([^)]*\):)')
    match = re.search(routing_pattern, content)
    if not match:
        print("  ✗ Could not find getRouting function")
        return False

    new_function = '''
    /**
     * Applies subscription chain (previous/next proxy) to an injected outbound.
     * Handles deduplication: if the same prev/next proxy is needed by multiple outbounds,
     * reuse the existing outbound instead of creating a new one.
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
        
        fun addChainOutbound(
            targetRemark: String?,
            chainType: String,
            chainTo: (V2rayConfig.OutboundBean) -> Unit
        ) {
            if (targetRemark.isNullOrEmpty()) return
            
            val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return
            val mapKey = "$chainType-$targetRemark"
            
            val existingTag = outboundTagMap[mapKey]
            if (existingTag != null) {
                chainTo(v2rayConfig.outbounds.first { it.tag == existingTag })
                LogUtil.d(AppConfig.TAG, "Reused $chainType outbound: $existingTag")
                return
            }
            
            val chainOutbound = convertProfile2Outbound(chainProfile) ?: return
            updateOutboundWithGlobalSettings(chainOutbound)
            
            val generatedTag = "chain-$chainType-${targetRemark.hashCode().toString(16).take(8)}"
            chainOutbound.tag = generatedTag
            outboundTagMap[mapKey] = generatedTag
            
            chainTo(chainOutbound)
            v2rayConfig.outbounds.add(chainOutbound)
            existingTags.add(generatedTag)
            LogUtil.d(AppConfig.TAG, "Created $chainType outbound: $generatedTag")
        }
        
        addChainOutbound(subItem.prevProfile, "prev") { prevOutbound ->
            outbound.ensureSockopt().dialerProxy = prevOutbound.tag
        }
        
        addChainOutbound(subItem.nextProfile, "next") { nextOutbound ->
            val originalTag = outbound.tag
            outbound.tag = "${originalTag}-orig"
            nextOutbound.ensureSockopt().dialerProxy = outbound.tag
            v2rayConfig.outbounds.add(0, nextOutbound)
        }
    }
'''
    content = content[:match.start()] + new_function + "\n" + content[match.start():]
    print("  ✓ Inserted applySubscriptionChain function")

    # --- 4. Modify getRouting to create outboundTagMap and pass it ---
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
        print("\n👉 Rebuild the app and test subscription chaining.")
    else:
        print("\n❌ Patching failed. Restore from backup.")


if __name__ == "__main__":
    main()

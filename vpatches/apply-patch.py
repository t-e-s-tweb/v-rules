#!/usr/bin/env python3
"""
Patches V2rayConfigManager.kt with subscription chaining (prev/next proxy) + deduplication.
Uses reliable insertion points from the working custom-outbound script.
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

    # --- 1. Add import for ensureSockopt if missing ---
    import_line = "import com.v2ray.ang.extension.ensureSockopt"
    if import_line not in content:
        # Find a good place to insert (after other imports)
        pattern = r'(import com\.v2ray\.ang\.extension\..*\n)'
        match = re.search(pattern, content)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + import_line + "\n" + content[insert_pos:]
            print("  Added import ensureSockopt")
        else:
            print("  ⚠ Could not find import block; ensureSockopt may already be resolved")

    # --- 2. Modify injectCustomOutbounds signature ---
    old_sig = "private fun injectCustomOutbounds(v2rayConfig: V2rayConfig) {"
    new_sig = "private fun injectCustomOutbounds(v2rayConfig: V2rayConfig, outboundTagMap: MutableMap<String, String> = mutableMapOf()) {"
    if old_sig in content:
        content = content.replace(old_sig, new_sig)
    else:
        print("  ✗ Could not find injectCustomOutbounds signature")
        return False

    # --- 3. Replace tag assignment block inside injectCustomOutbounds ---
    old_block = """            updateOutboundWithGlobalSettings(outbound)
            outbound.tag = tag
            v2rayConfig.outbounds.add(outbound)
            existingTags.add(tag)
            LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$tag'")"""
    new_block = """            updateOutboundWithGlobalSettings(outbound)
            
            // Generate unique tag for deduplication tracking
            val injectedTag = if (tag in outboundTagMap) {
                outboundTagMap[tag]!!
            } else {
                val newTag = "custom-${tag.hashCode().toString(16).take(8)}"
                outboundTagMap[tag] = newTag
                newTag
            }
            outbound.tag = injectedTag
            
            // Apply subscription chain (prev/next proxy) if applicable
            applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)
            
            v2rayConfig.outbounds.add(outbound)
            existingTags.add(injectedTag)
            LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$injectedTag', original='$tag'")"""
    if old_block in content:
        content = content.replace(old_block, new_block)
    else:
        print("  ✗ Could not find outbound tag assignment block")
        return False

    # --- 4. Insert applySubscriptionChain function before getRouting ---
    routing_pattern = r'(\n\s*private fun getRouting\([^)]*\):)'
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
    print("  Inserted applySubscriptionChain")

    # --- 5. Modify getRouting to create outboundTagMap and pass it ---
    old_call = "            injectCustomOutbounds(v2rayConfig)"
    new_call = """            val outboundTagMap = mutableMapOf<String, String>()
            injectCustomOutbounds(v2rayConfig, outboundTagMap)"""
    if old_call in content:
        content = content.replace(old_call, new_call)
    else:
        print("  ✗ Could not find injectCustomOutbounds call in getRouting")
        return False

    # --- 6. Write back ---
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

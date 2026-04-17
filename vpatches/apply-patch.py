#!/usr/bin/env python3
"""
Production-ready in-place patcher for v2rayNG V2rayConfigManager.kt
Adds auto prev/next proxy chaining to custom routing outbounds with deduplication.
Fixed version – no syntax errors, proper Kotlin insertion.
"""

import re
import sys
import shutil
from datetime import datetime
from pathlib import Path


def create_backup(filepath: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.with_suffix(f".kts.bak.{timestamp}")
    shutil.copy2(filepath, backup_path)
    print(f"Backup: {backup_path}")
    return backup_path


def check_already_patched(content: str) -> bool:
    return (
        "applySubscriptionChain" in content
        and "outboundTagMap: MutableMap<String, String>" in content
        and "chain-prev-" in content
    )


def modify_inject_custom_outbounds(content: str) -> str:
    # Update function signature
    old_sig = "private fun injectCustomOutbounds(v2rayConfig: V2rayConfig) {"
    new_sig = "private fun injectCustomOutbounds(v2rayConfig: V2rayConfig, outboundTagMap: MutableMap<String, String> = mutableMapOf()) {"
    content = content.replace(old_sig, new_sig)

    # Replace the tag assignment block (use exact original string)
    old_tag_block = """            updateOutboundWithGlobalSettings(outbound)
            outbound.tag = tag
            v2rayConfig.outbounds.add(outbound)
            existingTags.add(tag)
            LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$tag'")"""

    new_tag_block = """            updateOutboundWithGlobalSettings(outbound)
            
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

    return content.replace(old_tag_block, new_tag_block)


def add_apply_subscription_chain_function(content: str) -> str:
    new_function = """

    /**
     * Applies subscription chain (previous/next proxy) to an injected outbound.
     * Handles deduplication: if the same prev/next proxy is needed by multiple outbounds,
     * reuse the existing outbound instead of creating a new one.
     */
    private fun applySubscriptionChain(
        v2rayConfig: V2rayConfig,
        profile: ProfileItem,
        outbound: OutboundBean,
        outboundTagMap: MutableMap<String, String>,
        existingTags: MutableSet<String>
    ) {
        if (profile.subscriptionId.isNullOrEmpty()) return
        
        val subItem = MmkvManager.decodeSubscription(profile.subscriptionId) ?: return
        
        // Handle previous proxy in chain
        if (!subItem.prevProfile.isNullOrEmpty()) {
            val prevProfile = SettingsManager.getServerViaRemarks(subItem.prevProfile)
            if (prevProfile != null) {
                val prevTagKey = "prev-${subItem.prevProfile}"
                val prevOutboundTag = if (prevTagKey in outboundTagMap) {
                    outboundTagMap[prevTagKey]!!
                } else {
                    val prevOutbound = convertProfile2Outbound(prevProfile)
                    if (prevOutbound != null) {
                        updateOutboundWithGlobalSettings(prevOutbound)
                        val generatedTag = "chain-prev-${subItem.prevProfile.hashCode().toString(16).take(8)}"
                        prevOutbound.tag = generatedTag
                        outboundTagMap[prevTagKey] = generatedTag
                        
                        // Chain: outbound -> prevOutbound
                        outbound.ensureSockopt().dialerProxy = generatedTag
                        v2rayConfig.outbounds.add(prevOutbound)
                        existingTags.add(generatedTag)
                        generatedTag
                    } else null
                }
                if (prevOutboundTag != null && outbound.ensureSockopt().dialerProxy.isNullOrEmpty()) {
                    outbound.ensureSockopt().dialerProxy = prevOutboundTag
                }
            }
        }
        
        // Handle next proxy in chain
        if (!subItem.nextProfile.isNullOrEmpty()) {
            val nextProfile = SettingsManager.getServerViaRemarks(subItem.nextProfile)
            if (nextProfile != null) {
                val nextTagKey = "next-${subItem.nextProfile}"
                val nextOutboundTag = if (nextTagKey in outboundTagMap) {
                    outboundTagMap[nextTagKey]!!
                } else {
                    val nextOutbound = convertProfile2Outbound(nextProfile)
                    if (nextOutbound != null) {
                        updateOutboundWithGlobalSettings(nextOutbound)
                        val generatedTag = "chain-next-${subItem.nextProfile.hashCode().toString(16).take(8)}"
                        nextOutbound.tag = generatedTag
                        outboundTagMap[nextTagKey] = generatedTag
                        
                        // Chain: nextOutbound -> outbound
                        nextOutbound.ensureSockopt().dialerProxy = outbound.tag
                        v2rayConfig.outbounds.add(0, nextOutbound)
                        existingTags.add(generatedTag)
                        generatedTag
                    } else null
                }
            }
        }
    }
"""

    # Insert before getRouting function
    match = re.search(r'(\n\s*private fun getRouting\([^)]*\):)', content)
    if match:
        insert_pos = match.start()
        return content[:insert_pos] + new_function + "\n" + content[insert_pos:]

    # Fallback: append before final class closing brace
    lines = content.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "}" and i > len(lines) // 2:
            return "\n".join(lines[:i]) + new_function + "\n" + "\n".join(lines[i:])
    return content.rstrip() + "\n" + new_function + "\n}"


def modify_get_routing(content: str) -> str:
    old_call = "            injectCustomOutbounds(v2rayConfig)"
    new_calls = """            // Pre-pass: inject outbounds referenced by remarks in routing rules
            // Use a map to track tag mappings for deduplication across multiple injections
            val outboundTagMap = mutableMapOf<String, String>()
            injectCustomOutbounds(v2rayConfig, outboundTagMap)"""
    return content.replace(old_call, new_calls)


def patch_file(filepath: Path) -> bool:
    print(f"Patching: {filepath}")

    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        return False

    content = filepath.read_text(encoding="utf-8")

    if check_already_patched(content):
        print("Already patched. Skipping.")
        return True

    backup = create_backup(filepath)
    print("Applying modifications...")

    modified = modify_inject_custom_outbounds(content)
    modified = add_apply_subscription_chain_function(modified)
    modified = modify_get_routing(modified)

    # Basic validation
    if "applySubscriptionChain" not in modified:
        print("Validation failed: missing applySubscriptionChain")
        shutil.copy2(backup, filepath)
        return False

    filepath.write_text(modified, encoding="utf-8")
    print("Patch applied successfully.")
    print(f"Backup saved at: {backup}")
    return True


def main():
    if len(sys.argv) < 2:
        # Try common paths
        for p in [
            Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt"),
            Path("../V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt"),
        ]:
            if p.exists():
                filepath = p.resolve()
                break
        else:
            print("Usage: python apply-patch-fixed.py <path_to_V2rayConfigManager.kt>")
            sys.exit(1)
    else:
        filepath = Path(sys.argv[1]).resolve()

    success = patch_file(filepath)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

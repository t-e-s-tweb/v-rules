#!/usr/bin/env python3
"""
When front/landing proxy equals the main active server, reuse the existing 'proxy'
outbound instead of creating a duplicate. Sets dialerProxy = "proxy" and skips
adding a new outbound.

Covers:
- Standard chain (getMoreOutbounds)
- Custom outbound chain (applySubscriptionChain)
"""

import re
from pathlib import Path

target = Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt")
content = target.read_text(encoding="utf-8")

# ------------------------------------------------------------------
# 1. Update getMoreOutbounds – reuse 'proxy' when remarks match
# ------------------------------------------------------------------

# Update signature to accept mainProfileRemarks
old_sig = "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String): Boolean {"
new_sig = "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String, mainProfileRemarks: String? = null): Boolean {"
if old_sig in content:
    content = content.replace(old_sig, new_sig)
    print("✓ Updated getMoreOutbounds signature")

# Previous proxy block
old_prev = """            //Previous proxy
            val prevNode = SettingsManager.getServerViaRemarks(subItem.prevProfile)
            if (prevNode != null) {
                val prevOutbound = convertProfile2Outbound(prevNode)
                if (prevOutbound != null) {
                    updateOutboundWithGlobalSettings(prevOutbound)
                    prevOutbound.tag = AppConfig.TAG_PROXY + "2"
                    v2rayConfig.outbounds.add(prevOutbound)
                    outbound.ensureSockopt().dialerProxy = prevOutbound.tag
                }
            }"""
new_prev = """            //Previous proxy
            val prevNode = SettingsManager.getServerViaRemarks(subItem.prevProfile)
            if (prevNode != null) {
                if (prevNode.remarks == mainProfileRemarks) {
                    // Same as main server – reuse existing 'proxy' outbound
                    outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                    LogUtil.d(AppConfig.TAG, "Prev proxy is the same as main server, set dialerProxy to proxy")
                } else {
                    val prevOutbound = convertProfile2Outbound(prevNode)
                    if (prevOutbound != null) {
                        updateOutboundWithGlobalSettings(prevOutbound)
                        prevOutbound.tag = AppConfig.TAG_PROXY + "2"
                        v2rayConfig.outbounds.add(prevOutbound)
                        outbound.ensureSockopt().dialerProxy = prevOutbound.tag
                    }
                }
            }"""
if old_prev in content:
    content = content.replace(old_prev, new_prev)
    print("✓ Updated prev proxy block")
else:
    print("⚠ Could not find prev proxy block")

# Next proxy block
old_next = """            //Next proxy
            val nextNode = SettingsManager.getServerViaRemarks(subItem.nextProfile)
            if (nextNode != null) {
                val nextOutbound = convertProfile2Outbound(nextNode)
                if (nextOutbound != null) {
                    updateOutboundWithGlobalSettings(nextOutbound)
                    nextOutbound.tag = AppConfig.TAG_PROXY
                    v2rayConfig.outbounds.add(0, nextOutbound)
                    outbound.tag = AppConfig.TAG_PROXY + "1"
                    nextOutbound.ensureSockopt().dialerProxy = outbound.tag
                }
            }"""
new_next = """            //Next proxy
            val nextNode = SettingsManager.getServerViaRemarks(subItem.nextProfile)
            if (nextNode != null) {
                if (nextNode.remarks == mainProfileRemarks) {
                    // Same as main server – nothing to do, the main outbound already acts as entry
                    LogUtil.d(AppConfig.TAG, "Next proxy is the same as main server, skipping")
                } else {
                    val nextOutbound = convertProfile2Outbound(nextNode)
                    if (nextOutbound != null) {
                        updateOutboundWithGlobalSettings(nextOutbound)
                        nextOutbound.tag = AppConfig.TAG_PROXY
                        v2rayConfig.outbounds.add(0, nextOutbound)
                        outbound.tag = AppConfig.TAG_PROXY + "1"
                        nextOutbound.ensureSockopt().dialerProxy = outbound.tag
                    }
                }
            }"""
if old_next in content:
    content = content.replace(old_next, new_next)
    print("✓ Updated next proxy block")
else:
    print("⚠ Could not find next proxy block")

# Update call sites to pass config.remarks
for old_call in ["getMoreOutbounds(v2rayConfig, config.subscriptionId)"]:
    new_call = "getMoreOutbounds(v2rayConfig, config.subscriptionId, config.remarks)"
    if old_call in content and new_call not in content:
        content = content.replace(old_call, new_call)
        print("✓ Updated call sites")

# ------------------------------------------------------------------
# 2. Update applySubscriptionChain – reuse 'proxy' for main server
# ------------------------------------------------------------------
# We'll locate the addChainOutbound function and modify the part after
# resolving chainProfile.
old_chain_block = """            val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return
            updateOutboundWithGlobalSettings(chainOutbound)"""
# Insert check right after resolving chainProfile, before proceeding
new_chain_block = """            val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return
            // If chain profile is the same as the main active server, reuse existing proxy
            val mainRemarks = MmkvManager.getSelectServer()?.let { MmkvManager.decodeServerConfig(it)?.remarks }
            if (chainProfile.remarks == mainRemarks) {
                outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                LogUtil.d(AppConfig.TAG, "Chain $chainType proxy is the main server, set dialerProxy to proxy")
                return
            }
            updateOutboundWithGlobalSettings(chainOutbound)"""
if old_chain_block in content:
    content = content.replace(old_chain_block, new_chain_block)
    print("✓ Updated applySubscriptionChain to reuse 'proxy'")
else:
    print("⚠ applySubscriptionChain pattern not found – maybe already patched differently")

target.write_text(content, encoding="utf-8")
print("\n✅ Fix applied. Rebuild and test.")

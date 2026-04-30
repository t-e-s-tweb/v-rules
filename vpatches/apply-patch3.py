#!/usr/bin/env python3
"""
Safe patch: reuse 'proxy' outbound when front/landing proxy = main server.
Apply AFTER the spinner + resolveCurrentServer patches.
"""

from pathlib import Path

target = Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt")
content = target.read_text(encoding="utf-8")

# 1. Add mainProfileRemarks parameter to getMoreOutbounds
content = content.replace(
    "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String): Boolean {",
    "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String, mainProfileRemarks: String? = null): Boolean {"
)

# 2. Update calls to pass config.remarks
content = content.replace(
    "getMoreOutbounds(v2rayConfig, config.subscriptionId)",
    "getMoreOutbounds(v2rayConfig, config.subscriptionId, config.remarks)"
)

# 3. Modify prev block - exact multi-line string as it exists after previous patches
old_prev = """            //Previous proxy
            val prevNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.prevProfile) ?: subItem.prevProfile)
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
            val prevNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.prevProfile) ?: subItem.prevProfile)
            if (prevNode != null) {
                if (prevNode.remarks == mainProfileRemarks) {
                    // Same as main server – reuse existing 'proxy' outbound
                    outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                    LogUtil.d(AppConfig.TAG, "Prev proxy is main server, set dialerProxy to proxy")
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
    print("✓ Patched prev proxy block")
else:
    print("✗ Could not find prev proxy block – please check the file")

# 4. Modify next block
old_next = """            //Next proxy
            val nextNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.nextProfile) ?: subItem.nextProfile)
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
            val nextNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.nextProfile) ?: subItem.nextProfile)
            if (nextNode != null) {
                if (nextNode.remarks == mainProfileRemarks) {
                    // Same as main server – nothing to add
                    LogUtil.d(AppConfig.TAG, "Next proxy is main server, skipping")
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
    print("✓ Patched next proxy block")
else:
    print("✗ Could not find next proxy block – please check the file")

# 5. Modify applySubscriptionChain – insert check after chainProfile line
old_chain_line = "val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return"
new_chain_insert = """val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return
            // If the chain profile is the same as the current main server, reuse existing proxy outbound
            val mainRemarks = MmkvManager.getSelectServer()?.let { MmkvManager.decodeServerConfig(it)?.remarks }
            if (chainProfile.remarks == mainRemarks) {
                outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                LogUtil.d(AppConfig.TAG, "Chain proxy is main server, set dialerProxy to proxy")
                return
            }"""
if old_chain_line in content:
    content = content.replace(old_chain_line, new_chain_insert)
    print("✓ Patched applySubscriptionChain")
else:
    print("✗ Could not find chainProfile line in applySubscriptionChain")

target.write_text(content, encoding="utf-8")
print("\n✅ Reuse proxy logic applied. Rebuild now.")

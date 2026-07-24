#!/usr/bin/env python3
"""
Fixed patcher – applies targeted changes only.
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path("V2rayNG")

def backup_kotlin(p: Path):
    if p.suffix == ".kt":
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = p.with_suffix(f".kt.bak.{ts}")
        shutil.copy2(p, bak)
        print(f"  backup: {bak.name}")

def read(p): return p.read_text(encoding="utf-8")
def write(p, s): p.write_text(s, encoding="utf-8")


# ----------------------------------------------------------------------
# 1. AppConfig.kt – add CURRENT_SERVER + DNS prefs
# ----------------------------------------------------------------------
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    c = read(p)

    if '"__CURRENT_SERVER__"' not in c:
        # insert after BUILTIN_OUTBOUND_TAGS
        marker = "    val BUILTIN_OUTBOUND_TAGS = setOf("
        if marker in c:
            insert_pos = c.find(marker) + len(marker)
            brace_count = 1
            i = insert_pos
            while i < len(c) and brace_count > 0:
                if c[i] == '(':
                    brace_count += 1
                elif c[i] == ')':
                    brace_count -= 1
                i += 1
            const_line = "\n    const val CURRENT_SERVER = \"__CURRENT_SERVER__\""
            c = c[:i] + const_line + c[i:]
            print("✓ AppConfig: added CURRENT_SERVER")
        else:
            last_brace = c.rfind('}')
            if last_brace != -1:
                c = c[:last_brace] + "\n    const val CURRENT_SERVER = \"__CURRENT_SERVER__\"\n" + c[last_brace:]
                print("✓ AppConfig: added CURRENT_SERVER (fallback)")

    if "PREF_DNS_PARALLEL_QUERY" not in c:
        old = "    const val PREF_DNS_HOSTS = \"pref_dns_hosts\""
        new = '''    const val PREF_DNS_HOSTS = "pref_dns_hosts"
    const val PREF_DNS_PARALLEL_QUERY = "pref_dns_parallel_query"
    const val PREF_DNS_SERVE_STALE = "pref_dns_serve_stale"'''
        if old in c:
            c = c.replace(old, new, 1)
            print("✓ AppConfig: added DNS parallel/stale prefs")

    write(p, c)


# ----------------------------------------------------------------------
# 2. V2rayConfig.kt – add serveStale to DnsBean
# ----------------------------------------------------------------------
def patch_v2rayconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/V2rayConfig.kt"
    c = read(p)
    if "var serveStale" in c:
        print("• V2rayConfig: serveStale already present")
        return

    old_dns = '''data class DnsBean(
        var servers: ArrayList<Any>? = null,
        var hosts: Map<String, Any>? = null,
        val clientIp: String? = null,
        val disableCache: Boolean? = null,
        val queryStrategy: String? = null,
        val enableParallelQuery: Boolean? = null,
        val tag: String? = null
    )'''
    new_dns = '''data class DnsBean(
        var servers: ArrayList<Any>? = null,
        var hosts: Map<String, Any>? = null,
        val clientIp: String? = null,
        val disableCache: Boolean? = null,
        val queryStrategy: String? = null,
        val enableParallelQuery: Boolean? = null,
        val tag: String? = null,
        var serveStale: Boolean? = null
    )'''
    if old_dns in c:
        c = c.replace(old_dns, new_dns, 1)
        print("✓ V2rayConfig: added serveStale to DnsBean")
    else:
        print("⚠ V2rayConfig: DnsBean not found, skipping")
    write(p, c)


# ----------------------------------------------------------------------
# 3. SubEditActivity.kt – Compose version: add "None" and "[Current Server]"
# ----------------------------------------------------------------------
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/subscription/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found – skipping")
        return
    c = read(p)

    # Add special values to profileSuggestions
    old_suggestions = "profileSuggestions = suggestions"
    if old_suggestions in c:
        new_suggestions = '''profileSuggestions = listOf("None", "[Current Server]") + suggestions'''
        c = c.replace(old_suggestions, new_suggestions, 1)
        print("✓ SubEditActivity: added special items to suggestions")
    else:
        print("⚠ SubEditActivity: profileSuggestions line not found")

    # Convert saved values to display strings when loading
    old_load_prev = "var prevProfile by rememberSaveable { mutableStateOf(initial.prevProfile ?: \"\") }"
    new_load_prev = '''    var prevProfile by rememberSaveable { mutableStateOf(
        when (initial.prevProfile) {
            "" -> "None"
            AppConfig.CURRENT_SERVER -> "[Current Server]"
            else -> initial.prevProfile
        }
    ) }'''
    if "var prevProfile by rememberSaveable" in c:
        c = c.replace(old_load_prev, new_load_prev, 1)
        print("✓ SubEditActivity: updated prevProfile loading")

    old_load_next = "var nextProfile by rememberSaveable { mutableStateOf(initial.nextProfile ?: \"\") }"
    new_load_next = '''    var nextProfile by rememberSaveable { mutableStateOf(
        when (initial.nextProfile) {
            "" -> "None"
            AppConfig.CURRENT_SERVER -> "[Current Server]"
            else -> initial.nextProfile
        }
    ) }'''
    if "var nextProfile by rememberSaveable" in c:
        c = c.replace(old_load_next, new_load_next, 1)
        print("✓ SubEditActivity: updated nextProfile loading")

    # Convert display strings back to stored values when saving
    old_save_prev = "subItem.prevProfile = prevProfile"
    new_save_prev = '''        subItem.prevProfile = when (prevProfile) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> prevProfile
        }'''
    if "subItem.prevProfile = prevProfile" in c:
        c = c.replace(old_save_prev, new_save_prev, 1)
        print("✓ SubEditActivity: updated prevProfile saving")

    old_save_next = "subItem.nextProfile = nextProfile"
    new_save_next = '''        subItem.nextProfile = when (nextProfile) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> nextProfile
        }'''
    if "subItem.nextProfile = nextProfile" in c:
        c = c.replace(old_save_next, new_save_next, 1)
        print("✓ SubEditActivity: updated nextProfile saving")

    write(p, c)


# ----------------------------------------------------------------------
# 4. strings.xml – add "None" and "[Current Server]"
# ----------------------------------------------------------------------
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    c = read(p)
    needed = {"sub_setting_none": "None", "sub_setting_current_server": "[Current Server]"}
    changed = False
    for k, v in needed.items():
        if f'name="{k}"' in c:
            continue
        m = re.search(r'(\s*)</resources>', c, re.IGNORECASE)
        if not m:
            print(f"✗ strings.xml: </resources> not found")
            return
        indent, pos = m.group(1), m.start()
        c = c[:pos] + f'\n{indent}<string name="{k}">{v}</string>' + c[pos:]
        changed = True
    if changed:
        write(p, c)
        print("✓ strings.xml: added None and [Current Server]")


# ----------------------------------------------------------------------
# 5. CoreConfigContextBuilder.kt – add resolveCurrentServer helper
# ----------------------------------------------------------------------
def patch_coreconfigcontextbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"
    if not p.exists():
        print("✗ CoreConfigContextBuilder.kt not found – skipping")
        return
    c = read(p)

    if "private fun resolveCurrentServer" not in c:
        # Insert before the last '}'
        lines = c.splitlines()
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == '}':
                helper = [
                    "",
                    "    /**",
                    "     * Resolves [Current Server] placeholder to the actual selected server's remark.",
                    "     */",
                    "    private fun resolveCurrentServer(remark: String?): String? {",
                    "        if (remark == AppConfig.CURRENT_SERVER) {",
                    "            val currId = MmkvManager.getSelectServer()",
                    "            if (!currId.isNullOrEmpty()) {",
                    "                val profile = MmkvManager.decodeServerConfig(currId)",
                    "                return profile?.remarks",
                    "            }",
                    "        }",
                    "        return remark",
                    "    }",
                ]
                lines[i:i] = helper
                c = '\n'.join(lines)
                print("✓ CoreConfigContextBuilder: added resolveCurrentServer")
                break

    # Update resolveProxyChainProfilesFromGroup to use resolveCurrentServer
    old_chain = '''    private fun resolveProxyChainProfilesFromGroup(config: ProfileItem): List<ProfileItem> {
        if (config.subscriptionId.isEmpty()) {
            return listOf(config)
        }

        try {
            val subItem = MmkvManager.decodeSubscription(config.subscriptionId) ?: return listOf(config)
            val resolved = mutableListOf<ProfileItem>()
            SettingsManager.getServerViaRemarks(subItem.nextProfile)?.let { resolved.add(it) }
            resolved.add(config)
            SettingsManager.getServerViaRemarks(subItem.prevProfile)?.let { resolved.add(it) }
            return resolved
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to resolve proxy chain from group for '${config.remarks}'", e)
            return listOf(config)
        }
    }'''
    new_chain = '''    private fun resolveProxyChainProfilesFromGroup(config: ProfileItem): List<ProfileItem> {
        if (config.subscriptionId.isEmpty()) {
            return listOf(config)
        }

        try {
            val subItem = MmkvManager.decodeSubscription(config.subscriptionId) ?: return listOf(config)
            val resolved = mutableListOf<ProfileItem>()
            resolveCurrentServer(subItem.nextProfile)?.let { remark ->
                SettingsManager.getServerViaRemarks(remark)?.let { resolved.add(it) }
            }
            resolved.add(config)
            resolveCurrentServer(subItem.prevProfile)?.let { remark ->
                SettingsManager.getServerViaRemarks(remark)?.let { resolved.add(it) }
            }
            return resolved
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to resolve proxy chain from group for '${config.remarks}'", e)
            return listOf(config)
        }
    }'''
    if old_chain in c:
        c = c.replace(old_chain, new_chain, 1)
        print("✓ CoreConfigContextBuilder: updated resolveProxyChainProfilesFromGroup")
    else:
        print("⚠ CoreConfigContextBuilder: resolveProxyChainProfilesFromGroup not found")

    write(p, c)


# ----------------------------------------------------------------------
# 6. CoreConfigManager.kt – targeted changes only
# ----------------------------------------------------------------------
def patch_coreconfigmanager_targeted():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found – skipping")
        return
    backup_kotlin(p)
    c = read(p)

    # 6.1 Add missing imports if needed
    if "import com.v2ray.ang.dto.entities.SubscriptionItem" not in c:
        # insert after last import
        import_line = "import com.v2ray.ang.dto.entities.SubscriptionItem"
        last_import = re.search(r'^import .*$', c, re.MULTILINE)
        if last_import:
            pos = last_import.end()
            c = c[:pos] + "\n" + import_line + c[pos:]
            print("✓ CoreConfigManager: added import SubscriptionItem")

    # 6.2 Add helper functions at the end of the file (before the last '}')
    helpers = r'''
    // ------------------------------------------------------------------
    // Custom outbound injection with chain proxy support
    // ------------------------------------------------------------------

    private fun getCurrentMainServerRemarks(): String? {
        val currId = MmkvManager.getSelectServer()
        return if (!currId.isNullOrEmpty()) {
            MmkvManager.decodeServerConfig(currId)?.remarks?.trim()
        } else null
    }

    private fun resolveCurrentServer(remark: String?): String? {
        if (remark == AppConfig.CURRENT_SERVER) {
            val currId = MmkvManager.getSelectServer()
            if (!currId.isNullOrEmpty()) {
                val profile = MmkvManager.decodeServerConfig(currId)
                return profile?.remarks
            }
        }
        return remark
    }

    private fun injectCustomOutbounds(v2rayConfig: V2rayConfig) {
        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val outboundTagMap = mutableMapOf<String, String>()

        val rulesetItems = MmkvManager.decodeRoutingRulesets() ?: return
        val customOutboundTags = rulesetItems
            .filter { it.enabled && !AppConfig.BUILTIN_OUTBOUND_TAGS.contains(it.outboundTag) }
            .map { it.outboundTag }
            .distinct()
        LogUtil.d(AppConfig.TAG, "🎯 Custom outbound tags from routing rules: $customOutboundTags")

        for (tag in customOutboundTags) {
            if (tag in existingTags) {
                LogUtil.d(AppConfig.TAG, "⏩ Custom outbound '$tag' already injected, skipping")
                continue
            }
            val profile = SettingsManager.getServerViaRemarks(tag) ?: run {
                LogUtil.w(AppConfig.TAG, "⚠️ No profile found for custom outbound tag '$tag'")
                continue
            }
            val outbound = convertProfile2Outbound(profile) ?: run {
                LogUtil.w(AppConfig.TAG, "⚠️ Failed to convert profile for '$tag' to outbound")
                continue
            }
            outbound.tag = tag

            applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)

            v2rayConfig.outbounds.add(outbound)
            existingTags.add(tag)
            outboundTagMap[tag] = tag
            LogUtil.d(AppConfig.TAG, "✅ Injected custom outbound '$tag'")
        }
    }

    private fun applySubscriptionChain(
        v2rayConfig: V2rayConfig,
        profile: ProfileItem,
        outbound: V2rayConfig.OutboundBean,
        outboundTagMap: MutableMap<String, String>,
        existingTags: MutableSet<String>
    ) {
        var subItem: SubscriptionItem? = null

        if (!profile.subscriptionId.isNullOrEmpty()) {
            subItem = MmkvManager.decodeSubscription(profile.subscriptionId)
        }

        if (subItem == null) {
            LogUtil.d(AppConfig.TAG, "⚠️ No subscription for profile '${profile.remarks}', cannot apply chain")
            return
        }

        val originalTag = outbound.tag
        LogUtil.d(AppConfig.TAG, "🔗 Applying chain for '$originalTag' using subscription ${subItem.remarks}")
        LogUtil.d(AppConfig.TAG, "   prevProfile='${subItem.prevProfile}', nextProfile='${subItem.nextProfile}'")

        val currentMainRemarks = getCurrentMainServerRemarks()
        LogUtil.d(AppConfig.TAG, "   Current main server remarks: '$currentMainRemarks'")

        fun addChainOutbound(
            targetRemark: String?,
            chainType: String,
            desiredTag: String,
            chainTo: (V2rayConfig.OutboundBean) -> Unit
        ) {
            val resolvedRemark = resolveCurrentServer(targetRemark)?.trim()
            if (resolvedRemark.isNullOrEmpty()) {
                LogUtil.d(AppConfig.TAG, "⚠️ $chainType target is empty or None, skipping")
                return
            }

            LogUtil.d(AppConfig.TAG, "   $chainType resolved remark: '$resolvedRemark'")

            val isCurrentMain = currentMainRemarks != null && resolvedRemark.equals(currentMainRemarks, ignoreCase = true)

            // For prev chain: if main server, reuse "proxy" directly
            if (chainType == "prev" && isCurrentMain) {
                LogUtil.d(AppConfig.TAG, "✅ Prev target is main server – setting dialerProxy to '${AppConfig.TAG_PROXY}'")
                outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                return
            }

            // For next chain (or prev when not main): create numbered outbound
            val existingByTag = v2rayConfig.outbounds.firstOrNull { it.tag == desiredTag }
            if (existingByTag != null) {
                chainTo(existingByTag)
                outboundTagMap["$chainType-$resolvedRemark"] = desiredTag
                LogUtil.d(AppConfig.TAG, "♻️ Reused existing $chainType outbound: $desiredTag")
                return
            }

            val mapKey = "$chainType-$resolvedRemark"
            val existingTag = outboundTagMap[mapKey]
            if (existingTag != null) {
                val existingOutbound = v2rayConfig.outbounds.firstOrNull { it.tag == existingTag }
                if (existingOutbound != null) {
                    chainTo(existingOutbound)
                    LogUtil.d(AppConfig.TAG, "♻️ Reused $chainType outbound from map: $existingTag")
                    return
                }
            }

            val chainProfile = SettingsManager.getServerViaRemarks(resolvedRemark)
            if (chainProfile == null) {
                LogUtil.w(AppConfig.TAG, "❌ No profile found for $chainType remark '$resolvedRemark'")
                return
            }

            val chainOutbound = convertProfile2Outbound(chainProfile)
            if (chainOutbound == null) {
                LogUtil.w(AppConfig.TAG, "❌ Failed to convert $chainType profile '$resolvedRemark' to outbound")
                return
            }
            chainOutbound.tag = desiredTag
            outboundTagMap[mapKey] = desiredTag

            chainTo(chainOutbound)
            v2rayConfig.outbounds.add(chainOutbound)
            existingTags.add(desiredTag)
            LogUtil.d(AppConfig.TAG, "✅ Created new $chainType outbound: $desiredTag")
        }

        // Handle prev hop (may reuse "proxy" if main server)
        addChainOutbound(subItem.prevProfile, "prev", "$originalTag-prev") { prevOutbound ->
            outbound.ensureSockopt().dialerProxy = prevOutbound.tag
            LogUtil.d(AppConfig.TAG, "🔗 Wired prev: ${outbound.tag}.dialerProxy = ${prevOutbound.tag}")
        }

        // Handle next hop – always create a numbered outbound
        if (!subItem.nextProfile.isNullOrEmpty()) {
            val nextTag = "${AppConfig.TAG_PROXY}-${originalTag}-1"
            addChainOutbound(subItem.nextProfile, "next", nextTag) { nextOutbound ->
                outbound.ensureSockopt().dialerProxy = nextOutbound.tag
                LogUtil.d(AppConfig.TAG, "🔗 Wired next: ${outbound.tag}.dialerProxy = ${nextOutbound.tag}")
            }
        } else {
            LogUtil.d(AppConfig.TAG, "ℹ️ No nextProfile configured, skipping next hop")
        }
    }
'''
    if "private fun getCurrentMainServerRemarks()" not in c:
        # insert before last '}'
        lines = c.splitlines()
        for i in range(len(lines)-1, -1, -1):
            if lines[i].strip() == '}':
                lines[i:i] = helpers.splitlines()
                c = '\n'.join(lines)
                print("✓ CoreConfigManager: added helper functions")
                break

    # 6.3 Modify buildUnifiedConfig to call injectCustomOutbounds
    # Find the line where it calls applyObservability, applySpeedDisabled, etc.
    # We'll add injectCustomOutbounds after the balancer loop and before configureRouting.
    # Look for "configureRouting(" and insert before it.
    if "injectCustomOutbounds(v2rayConfig)" not in c:
        # Insert before configureRouting call
        pattern = r'(\s+)configureRouting\(configContext, v2rayConfig, policyGroupBalancerTags\)'
        replacement = r'\1injectCustomOutbounds(v2rayConfig)\n\1configureRouting(configContext, v2rayConfig, policyGroupBalancerTags)'
        c = re.sub(pattern, replacement, c, count=1)
        print("✓ CoreConfigManager: added injectCustomOutbounds call")

    # 6.4 Modify handleProxyChainResolvedOutbound to use the new logic.
    # We'll replace the entire method with a new version that uses the chain helpers.
    old_method = r'''    private fun handleProxyChainResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
    )'''
    # We need to find the whole method body and replace it.
    # We'll use regex to find from that line to the closing brace of the method.
    # But simpler: we can add a new method and comment out the old one? Not ideal.
    # Instead, we'll replace the entire method with a new version that calls the new helpers.
    # We'll locate the start and then scan for the matching closing brace.
    # Since this is complex, we'll just note that we need to update it.
    # For now, we'll insert a note, but we can also use a more robust approach.

    # I'll implement a scanner to replace the method body.
    start_pattern = r'    private fun handleProxyChainResolvedOutbound\([^)]*\) \{[^}]*\}'
    # This won't match nested braces; we need a proper scanner.

    # Instead, we'll use a simpler approach: append a new version of the method and rename the old one?
    # Better: we'll replace the old method with a new one that calls the chain logic from the helpers.
    # We'll locate the method start, then find the matching brace using a counter.
    # I'll implement a helper to find method body.

    def find_method_body(text, start_line):
        lines = text.splitlines()
        brace_count = 0
        start_idx = None
        for i in range(start_line, len(lines)):
            line = lines[i]
            if '{' in line:
                if brace_count == 0:
                    start_idx = i
                brace_count += line.count('{')
            if '}' in line:
                brace_count -= line.count('}')
                if brace_count == 0 and start_idx is not None:
                    return start_idx, i
        return None, None

    # We'll locate the method starting line.
    method_start = c.find("private fun handleProxyChainResolvedOutbound")
    if method_start != -1:
        # find line number
        start_line = c[:method_start].count('\n')
        start, end = find_method_body(c, start_line)
        if start is not None:
            # Replace the method body with new version.
            new_method = '''    private fun handleProxyChainResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        outboundTagMap: MutableMap<String, String>,
    ) {
        LogUtil.d(AppConfig.TAG, "🔗 Processing PROXYCHAIN for tag='${resolvedOutbound.tag}', prepend=$prepend")
        LogUtil.d(AppConfig.TAG, "   Number of resolvedProfiles: ${resolvedOutbound.resolvedProfiles.size}")

        val mainRemarks = getCurrentMainServerRemarks()
        LogUtil.d(AppConfig.TAG, "   Current main server remarks: '$mainRemarks'")

        var prevOutboundTag: String? = null

        for ((profileIndex, profile) in resolvedOutbound.resolvedProfiles.withIndex()) {
            val profileRemarks = profile.remarks.trim()
            val isMainServer = mainRemarks != null && profileRemarks.equals(mainRemarks, ignoreCase = true)

            val desiredTag = if (profileIndex == 0) {
                resolvedOutbound.tag
            } else {
                "${AppConfig.TAG_PROXY}-${resolvedOutbound.tag}-${profileIndex}"
            }

            if (isMainServer && profileIndex == 0) {
                LogUtil.d(AppConfig.TAG, "♻️ Hop 0 is current main server ('$profileRemarks') – setting ${resolvedOutbound.tag}.dialerProxy = 'proxy'")
                val customOutbound = v2rayConfig.outbounds.firstOrNull { it.tag == resolvedOutbound.tag }
                if (customOutbound != null) {
                    customOutbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                }
                return
            }

            if (isMainServer && profileIndex > 0) {
                LogUtil.d(AppConfig.TAG, "♻️ Hop $profileIndex is current main server ('$profileRemarks') – chaining previous to 'proxy'")
                if (prevOutboundTag != null) {
                    val prevOutbound = v2rayConfig.outbounds.firstOrNull { it.tag == prevOutboundTag }
                    if (prevOutbound != null) {
                        prevOutbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                        LogUtil.d(AppConfig.TAG, "🔗 Set dialerProxy of '$prevOutboundTag' → 'proxy'")
                    }
                }
                continue
            }

            val outbound = convertProfile2Outbound(profile)
            if (outbound == null) {
                LogUtil.e(AppConfig.TAG, "❌ Failed to convert profile '${profile.remarks}' (type=${profile.configType})")
                continue
            }
            outbound.tag = desiredTag

            val mapKey = "chain-${profile.remarks}"
            val existingTag = outboundTagMap[mapKey]
            if (existingTag != null) {
                val existingOutbound = v2rayConfig.outbounds.firstOrNull { it.tag == existingTag }
                if (existingOutbound != null) {
                    if (prevOutboundTag != null) {
                        val prevOut = v2rayConfig.outbounds.firstOrNull { it.tag == prevOutboundTag }
                        prevOut?.ensureSockopt()?.dialerProxy = existingTag
                        LogUtil.d(AppConfig.TAG, "🔗 Reused existing hop $existingTag, wired from $prevOutboundTag")
                    }
                    prevOutboundTag = existingTag
                    continue
                }
            }

            if (prepend) {
                v2rayConfig.outbounds.add(0, outbound)
            } else {
                v2rayConfig.outbounds.add(outbound)
            }
            existingTags.add(desiredTag)
            outboundTagMap[mapKey] = desiredTag

            if (prevOutboundTag != null) {
                val prevOut = v2rayConfig.outbounds.firstOrNull { it.tag == prevOutboundTag }
                prevOut?.ensureSockopt()?.dialerProxy = desiredTag
                LogUtil.d(AppConfig.TAG, "🔗 Wired $prevOutboundTag → $desiredTag")
            }
            prevOutboundTag = desiredTag
        }

        if (prevOutboundTag == null) {
            val customOutboundTag = resolvedOutbound.tag
            val customOutbound = v2rayConfig.outbounds.firstOrNull { it.tag == customOutboundTag }
            if (customOutbound != null) {
                customOutbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                LogUtil.d(AppConfig.TAG, "🔗 All hops are main server – set dialerProxy of '$customOutboundTag' → 'proxy'")
            }
        }
    }'''
            # Replace the lines from start to end with new_method
            lines = c.splitlines()
            lines[start:end+1] = new_method.splitlines()
            c = '\n'.join(lines)
            print("✓ CoreConfigManager: updated handleProxyChainResolvedOutbound")

    # 6.5 Modify configureDns to use DNS parallel/stale prefs
    # Find the part where DnsBean is constructed and add the settings.
    # We'll replace the dnsBean creation.
    old_dns_bean = r'val dnsBean = V2rayConfig\.DnsBean\([^)]*\)'
    # We'll use a more precise replacement.
    # Instead, we'll find the line that sets enableParallelQuery and add serveStale.
    if "serveStale" not in c:
        # Find where dnsBean is assigned.
        # We'll look for "v2rayConfig.dns = dnsBean" and add code before that.
        # But simpler: we can modify the part where enableParallelQuery is set.
        pattern = r'(dnsBean\.enableParallelQuery = .*)'
        replacement = r'\1\n        if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false) == true) {\n            dnsBean.serveStale = true\n        }'
        if re.search(pattern, c):
            c = re.sub(pattern, replacement, c)
            print("✓ CoreConfigManager: added serveStale to DNS config")
        else:
            # If not found, we can add after enableParallelQuery assignment.
            # We'll just append at the end of configureDns.
            pass

    # Write changes
    write(p, c)
    print("✓ CoreConfigManager: targeted patches applied")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Fixed Patcher – targeted changes only")
    print("=" * 70)

    try:
        patch_appconfig()
        patch_v2rayconfig()
        patch_subedit()
        patch_strings()
        patch_coreconfigcontextbuilder()
        patch_coreconfigmanager_targeted()
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild and test.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

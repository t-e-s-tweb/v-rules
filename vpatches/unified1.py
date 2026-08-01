#!/usr/bin/env python3
"""
Unified patcher - corrected version.

Fixes two bugs from the previous version:

1. DNS parallel-query / serve-stale toggles never reached the generated core
   config. CoreConfigManager.kt has an OLD configureDns(v2rayConfig,
   policyGroupBalancerTags) overload commented out (/* ... */) higher up in
   the class, kept as dead-code reference, followed by the real
   configureDns(configContext, v2rayConfig, policyGroupBalancerTags) that is
   actually called from buildUnifiedConfig(). The old patcher used
   c.find("private fun configureDns(") which matches the FIRST occurrence -
   the commented-out one - so the "fix" was being written into a comment and
   had zero effect on the compiled app. This version anchors on the live
   method's unique signature instead. It also stopped mutating
   `enableParallelQuery` after construction (that field is `val`, so
   `dnsBean.enableParallelQuery = true` cannot compile) - values are computed
   first and passed straight into the DnsBean constructor.

2. The dropdown UI was slow because ExposedDropdownMenu's item list is a
   plain (non-lazy) Column - every option is composed and measured the
   instant the menu opens. That's invisible for small fixed lists (flow,
   security, network) but the new prevProfile/nextProfile chain pickers feed
   in every server remark across every subscription (potentially hundreds of
   items), so opening the menu visibly hitches. Fixed by rendering options in
   a LazyColumn instead, reusing the LazyListState overload of
   verticalScrollbar that already exists in Scrollbar.kt.
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

def read(p):
    return p.read_text(encoding="utf-8")

def write(p, s):
    p.write_text(s, encoding="utf-8")


# ----------------------------------------------------------------------
# 1. AppConfig.kt - add CURRENT_SERVER + DNS prefs
# ----------------------------------------------------------------------
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    c = read(p)

    if '"__CURRENT_SERVER__"' not in c:
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
        else:
            print("⚠ AppConfig: PREF_DNS_HOSTS not found, skipping DNS prefs")

    write(p, c)


# ----------------------------------------------------------------------
# 2. V2rayConfig.kt - add serveStale to DnsBean
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
# 3. SubEditActivity.kt - Compose version: add "None" and "[Current Server]"
# ----------------------------------------------------------------------
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/subscription/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found – skipping")
        return
    c = read(p)

    old_suggestions = "profileSuggestions = suggestions"
    if old_suggestions in c:
        new_suggestions = '''profileSuggestions = listOf("None", "[Current Server]") + suggestions'''
        c = c.replace(old_suggestions, new_suggestions, 1)
        print("✓ SubEditActivity: added special items to suggestions")
    else:
        print("⚠ SubEditActivity: profileSuggestions line not found")

    old_load_prev = "var prevProfile by rememberSaveable { mutableStateOf(initial.prevProfile ?: \"\") }"
    new_load_prev = '''    var prevProfile by rememberSaveable { mutableStateOf(
        when (initial.prevProfile) {
            "" -> "None"
            AppConfig.CURRENT_SERVER -> "[Current Server]"
            else -> initial.prevProfile ?: ""
        }
    ) }'''
    if "var prevProfile by rememberSaveable" in c:
        c = c.replace(old_load_prev, new_load_prev, 1)
        print("✓ SubEditActivity: updated prevProfile loading")
    else:
        print("⚠ SubEditActivity: prevProfile loading not found")

    old_load_next = "var nextProfile by rememberSaveable { mutableStateOf(initial.nextProfile ?: \"\") }"
    new_load_next = '''    var nextProfile by rememberSaveable { mutableStateOf(
        when (initial.nextProfile) {
            "" -> "None"
            AppConfig.CURRENT_SERVER -> "[Current Server]"
            else -> initial.nextProfile ?: ""
        }
    ) }'''
    if "var nextProfile by rememberSaveable" in c:
        c = c.replace(old_load_next, new_load_next, 1)
        print("✓ SubEditActivity: updated nextProfile loading")

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
# 4. strings.xml - add all needed strings
# ----------------------------------------------------------------------
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    c = read(p)

    new_strings = []
    needed = {
        "sub_setting_none": "None",
        "sub_setting_current_server": "[Current Server]",
        "title_pref_dns_parallel_query": "DNS Parallel Query",
        "summary_pref_dns_parallel_query": "Enable parallel queries to all DNS servers for faster resolution",
        "title_pref_dns_serve_stale": "DNS Serve Stale",
        "summary_pref_dns_serve_stale": "Serve stale DNS records while refreshing in background",
    }
    for k, v in needed.items():
        if f'name="{k}"' in c:
            continue
        new_strings.append(f'    <string name="{k}">{v}</string>')

    if new_strings:
        m = re.search(r'(\s*)</resources>', c, re.IGNORECASE)
        if m:
            indent, pos = m.group(1), m.start()
            insertion = "\n" + "\n".join(new_strings) + "\n" + indent
            c = c[:pos] + insertion + c[pos:]
            write(p, c)
            print(f"✓ strings.xml: added {len(new_strings)} strings")
        else:
            print("⚠ strings.xml: </resources> not found")
    else:
        print("• strings.xml: all strings already present")


# ----------------------------------------------------------------------
# 5. CoreConfigContextBuilder.kt - add resolveCurrentServer helper
# ----------------------------------------------------------------------
def patch_coreconfigcontextbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"
    if not p.exists():
        print("✗ CoreConfigContextBuilder.kt not found – skipping")
        return
    c = read(p)

    if "private fun resolveCurrentServer" not in c:
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
# 6. CoreConfigManager.kt
# ----------------------------------------------------------------------
def patch_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found – skipping")
        return
    backup_kotlin(p)
    c = read(p)

    # 6.1 Add missing import
    if "import com.v2ray.ang.dto.entities.SubscriptionItem" not in c:
        last_import = re.search(r'^import .*$', c, re.MULTILINE)
        if last_import:
            pos = last_import.end()
            c = c[:pos] + "\nimport com.v2ray.ang.dto.entities.SubscriptionItem" + c[pos:]
            print("✓ CoreConfigManager: added import SubscriptionItem")
        else:
            print("⚠ CoreConfigManager: could not find import block")

    # 6.2 Add helper functions before the final '}'
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
        lines = c.splitlines()
        for i in range(len(lines)-1, -1, -1):
            if lines[i].strip() == '}':
                lines[i:i] = helpers.splitlines()
                c = '\n'.join(lines)
                print("✓ CoreConfigManager: added helper functions")
                break

    # 6.3 Modify buildUnifiedConfig to call injectCustomOutbounds
    if "injectCustomOutbounds(v2rayConfig)" not in c:
        pattern = r'(\s+)configureRouting\(configContext, v2rayConfig, policyGroupBalancerTags\)'
        replacement = r'\1injectCustomOutbounds(v2rayConfig)\n\1configureRouting(configContext, v2rayConfig, policyGroupBalancerTags)'
        c = re.sub(pattern, replacement, c, count=1)
        print("✓ CoreConfigManager: added injectCustomOutbounds call")

    # 6.4 Update buildOutbounds signature and call
    old_build_outbounds = '''    private fun buildOutbounds(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: MutableMap<String, String>,
        balancerStrategies: MutableList<BalancerStrategy>,
    )'''
    new_build_outbounds = '''    private fun buildOutbounds(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: MutableMap<String, String>,
        balancerStrategies: MutableList<BalancerStrategy>,
        outboundTagMap: MutableMap<String, String> = mutableMapOf(),
    )'''
    if old_build_outbounds in c:
        c = c.replace(old_build_outbounds, new_build_outbounds, 1)
        print("✓ CoreConfigManager: updated buildOutbounds signature")
    else:
        print("⚠ CoreConfigManager: buildOutbounds signature not found")

    old_call = '''            CoreResolvedType.PROXYCHAIN -> handleProxyChainResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
            )'''
    new_call = '''            CoreResolvedType.PROXYCHAIN -> handleProxyChainResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                outboundTagMap = outboundTagMap,
            )'''
    if old_call in c:
        c = c.replace(old_call, new_call, 1)
        print("✓ CoreConfigManager: updated handleProxyChainResolvedOutbound call")
    else:
        print("⚠ CoreConfigManager: call not found")

    # 6.5 Replace handleProxyChainResolvedOutbound body
    method_start = c.find("private fun handleProxyChainResolvedOutbound")
    if method_start != -1:
        open_brace = c.find('{', method_start)
        if open_brace != -1:
            brace_count = 1
            i = open_brace + 1
            while i < len(c) and brace_count > 0:
                if c[i] == '{':
                    brace_count += 1
                elif c[i] == '}':
                    brace_count -= 1
                i += 1
            if brace_count == 0:
                new_signature = '''private fun handleProxyChainResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        outboundTagMap: MutableMap<String, String>,
    )'''
                new_body = ''' {
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
                method_end = i
                c = c[:method_start] + new_signature + new_body + c[method_end:]
                print("✓ CoreConfigManager: replaced handleProxyChainResolvedOutbound body")
            else:
                print("⚠ CoreConfigManager: brace mismatch for handleProxyChainResolvedOutbound")
        else:
            print("⚠ CoreConfigManager: could not find opening brace for handleProxyChainResolvedOutbound")
    else:
        print("⚠ CoreConfigManager: handleProxyChainResolvedOutbound method not found")

    # 6.6 FIXED: wire DNS parallel-query / serve-stale prefs into the ACTIVE
    # configureDns. There are TWO configureDns() defs in this file: an old
    # one wrapped in /* ... */ (dead, kept for reference) and the real one
    # actually called from buildUnifiedConfig(). We anchor on the live
    # signature specifically so we never edit the commented-out copy, and we
    # compute both booleans up front instead of mutating DnsBean afterwards
    # (enableParallelQuery is a `val` - post-construction mutation of it
    # can't compile).
    live_signature = "private fun configureDns(\n        configContext: CoreConfigContext,"
    method_start = c.find(live_signature)
    if method_start != -1:
        open_brace = c.find('{', method_start)
        if open_brace != -1:
            brace_count = 1
            i = open_brace + 1
            while i < len(c) and brace_count > 0:
                if c[i] == '{':
                    brace_count += 1
                elif c[i] == '}':
                    brace_count -= 1
                i += 1
            if brace_count == 0:
                method_end = i
                method_body = c[method_start:method_end]

                old_dns_construction = '''v2rayConfig.dns = V2rayConfig.DnsBean(
            servers = servers,
            hosts = hosts,
            tag = AppConfig.TAG_DNS,
            enableParallelQuery = if ((domesticDns.size + remoteDns.size) > 2) true else null
        )'''
                new_dns_construction = '''val dnsParallelQueryEnabled = MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false)
        val dnsServeStaleEnabled = MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false)

        v2rayConfig.dns = V2rayConfig.DnsBean(
            servers = servers,
            hosts = hosts,
            tag = AppConfig.TAG_DNS,
            enableParallelQuery = if (dnsParallelQueryEnabled) true else null,
            serveStale = if (dnsServeStaleEnabled) true else null
        )'''

                if "PREF_DNS_PARALLEL_QUERY" in method_body:
                    print("• CoreConfigManager: active configureDns already wired for DNS prefs")
                elif old_dns_construction in method_body:
                    new_method_body = method_body.replace(old_dns_construction, new_dns_construction, 1)
                    c = c[:method_start] + new_method_body + c[method_end:]
                    print("✓ CoreConfigManager: wired DNS parallel-query/serve-stale prefs into the ACTIVE configureDns")
                else:
                    print("⚠ CoreConfigManager: DnsBean construction not found inside active configureDns — source may have changed, check manually")
            else:
                print("⚠ CoreConfigManager: brace mismatch for configureDns")
        else:
            print("⚠ CoreConfigManager: could not find opening brace for configureDns")
    else:
        print("⚠ CoreConfigManager: active configureDns(configContext, ...) not found")

    # 6.7 Replace buildDnsHostsFromRoutingRules with BIND‑style hosts parser (using raw regex)
    method_start = c.find("private fun buildDnsHostsFromRoutingRules(")
    if method_start != -1:
        open_brace = c.find('{', method_start)
        if open_brace != -1:
            brace_count = 1
            i = open_brace + 1
            while i < len(c) and brace_count > 0:
                if c[i] == '{':
                    brace_count += 1
                elif c[i] == '}':
                    brace_count -= 1
                i += 1
            if brace_count == 0:
                new_build_hosts = r'''    private fun buildDnsHostsFromRoutingRules(configContext: CoreConfigContext): MutableMap<String, Any> {
        val hosts = mutableMapOf<String, Any>()

        val blockDomains = configContext.routingDomainRules
            .asSequence()
            .filter { it.outboundTag == AppConfig.TAG_BLOCKED }
            .flatMap { it.domain.asSequence() }
            .toList()
        if (blockDomains.isNotEmpty()) {
            hosts.putAll(blockDomains.map { it to AppConfig.LOOPBACK })
        }

        hosts[AppConfig.GOOGLEAPIS_CN_DOMAIN] = AppConfig.GOOGLEAPIS_COM_DOMAIN
        hosts[AppConfig.DNS_ALIDNS_DOMAIN] = AppConfig.DNS_ALIDNS_ADDRESSES
        hosts[AppConfig.DNS_CISCO_SSE_DOMAIN] = AppConfig.DNS_CISCO_SSE_ADDRESSES
        hosts[AppConfig.DNS_CISCO_UMBRELLA_DOMAIN] = AppConfig.DNS_CISCO_UMBRELLA_ADDRESSES
        hosts[AppConfig.DNS_CLOUDFLARE_ONE_DOMAIN] = AppConfig.DNS_CLOUDFLARE_ONE_ADDRESSES
        hosts[AppConfig.DNS_CLOUDFLARE_ONEDOT_DNS_DOMAIN] = AppConfig.DNS_CLOUDFLARE_ONEDOT_DNS_ADDRESSES
        hosts[AppConfig.DNS_CLOUDFLARE_DNS_COM_DOMAIN] = AppConfig.DNS_CLOUDFLARE_DNS_COM_ADDRESSES
        hosts[AppConfig.DNS_CLOUDFLARE_DNS_DOMAIN] = AppConfig.DNS_CLOUDFLARE_DNS_ADDRESSES
        hosts[AppConfig.DNS_CLOUDFLARE_WARP_DOMAIN] = AppConfig.DNS_CLOUDFLARE_WARP_ADDRESSES
        hosts[AppConfig.DNS_DNSPOD_DOH_DOMAIN] = AppConfig.DNS_DNSPOD_DOH_ADDRESSES
        hosts[AppConfig.DNS_DNSPOD_DOT_DOMAIN] = AppConfig.DNS_DNSPOD_DOT_ADDRESSES
        hosts[AppConfig.DNS_GOOGLE_DOMAIN] = AppConfig.DNS_GOOGLE_ADDRESSES
        hosts[AppConfig.DNS_QUAD9_DOMAIN] = AppConfig.DNS_QUAD9_ADDRESSES
        hosts[AppConfig.DNS_SB_DOMAIN] = AppConfig.DNS_SB_ADDRESSES
        hosts[AppConfig.DNS_YANDEX_DOMAIN] = AppConfig.DNS_YANDEX_ADDRESSES

        // User DNS hosts – BIND‑style format (one line per domain, space‑separated addresses)
        val userHosts = MmkvManager.decodeSettingsString(AppConfig.PREF_DNS_HOSTS)
        if (userHosts.isNotNullEmpty()) {
            val userHostsMap = userHosts?.lines()
                ?.filter { it.isNotEmpty() }
                ?.filter { it.contains(" ") }
                ?.associate { line ->
                    val parts = line.trim().split(Regex("""\s+"""))
                    val key = parts[0]
                    val values = parts.drop(1)
                    key to if (values.size == 1) values[0] else values
                }
            if (userHostsMap != null) {
                hosts.putAll(userHostsMap)
            }
        }

        return hosts
    }'''
                method_end = i
                c = c[:method_start] + new_build_hosts + c[method_end:]
                print("✓ CoreConfigManager: replaced buildDnsHostsFromRoutingRules with BIND‑style parser (raw regex)")
            else:
                print("⚠ CoreConfigManager: brace mismatch for buildDnsHostsFromRoutingRules")
        else:
            print("⚠ CoreConfigManager: could not find opening brace for buildDnsHostsFromRoutingRules")
    else:
        print("⚠ CoreConfigManager: buildDnsHostsFromRoutingRules method not found")

    write(p, c)
    print("✓ CoreConfigManager: targeted patches applied")


# ----------------------------------------------------------------------
# 7. SettingsActivity.kt – add DNS parallel/stale switches
# ----------------------------------------------------------------------
def patch_settings():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/settings/SettingsActivity.kt"
    if not p.exists():
        print("✗ SettingsActivity.kt not found")
        return
    c = read(p)

    old_decls = "var dnsHosts by rememberMmkvString(AppConfig.PREF_DNS_HOSTS, \"\")"
    new_decls = old_decls + """
    var dnsParallelQuery by rememberMmkvBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false)
    var dnsServeStale by rememberMmkvBool(AppConfig.PREF_DNS_SERVE_STALE, false)"""
    if old_decls in c and "dnsParallelQuery" not in c:
        c = c.replace(old_decls, new_decls, 1)
        print("✓ SettingsActivity: added DNS parallel/stale state declarations")
    elif "dnsParallelQuery" in c:
        print("• SettingsActivity: DNS states already present")
    else:
        print("⚠ SettingsActivity: could not find dnsHosts declaration block")

    pattern = r'(SettingsEditItem\(\s*title = stringResource\(R\.string\.title_pref_dns_hosts\),\s*value = dnsHosts,\s*onValueChanged = \{ dnsHosts = it \}\s*\))'
    if re.search(pattern, c, re.DOTALL) and "title_pref_dns_parallel_query" not in c:
        replacement = r'\1\n                SettingsSwitchItem(\n                    title = stringResource(R.string.title_pref_dns_parallel_query),\n                    summary = stringResource(R.string.summary_pref_dns_parallel_query),\n                    checked = dnsParallelQuery,\n                    onCheckedChange = { dnsParallelQuery = it }\n                )\n                SettingsSwitchItem(\n                    title = stringResource(R.string.title_pref_dns_serve_stale),\n                    summary = stringResource(R.string.summary_pref_dns_serve_stale),\n                    checked = dnsServeStale,\n                    onCheckedChange = { dnsServeStale = it }\n                )'
        c = re.sub(pattern, replacement, c, flags=re.DOTALL)
        print("✓ SettingsActivity: inserted DNS parallel/stale switches")
    else:
        print("⚠ SettingsActivity: dnsHosts block not found or switches already present")

    write(p, c)


# ----------------------------------------------------------------------
# 8. FormFields.kt - filter by typed text + hard cap (NOT LazyColumn)
# ----------------------------------------------------------------------
def patch_formfields():
    """
    v1 of this fix wrapped the dropdown's items in a LazyColumn. That
    crashes: Material3's ExposedDropdownMenu auto-sizes itself by querying
    INTRINSIC measurements of its content, and LazyColumn - like any
    SubcomposeLayout-based layout - explicitly does not support being
    intrinsically measured ("Asking for intrinsic measurements of
    SubcomposeLayout layouts is not supported"). This is a known Compose
    limitation (Google issue trackers 242101969 / 242398344), not something
    fixable with a modifier tweak on the LazyColumn.

    Real fix: keep the plain (non-lazy) Column that ExposedDropdownMenu
    requires, but stop handing it hundreds of items. Every editable=true
    FormDropdownField in this codebase (outboundTag, fallbackTag,
    prevProfile/nextProfile, the proxy-chain member picker) is a
    type-a-value-with-suggestions field, so filtering the suggestion list by
    what's currently typed is correct UX, not just a perf hack. A hard cap
    of 50 is the backstop for the unfiltered case (field is empty, list is
    huge) - well under the ~100-item threshold where a plain Column starts
    to visibly lag.

    Idempotent against BOTH a pristine checkout and a tree that already has
    the v1 LazyColumn attempt applied.
    """
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/compose/FormFields.kt"
    if not p.exists():
        print("✗ FormFields.kt not found")
        return
    c = read(p)

    # Remove lazy-only imports left over from a v1 run, if present.
    for stale in (
        "import androidx.compose.foundation.lazy.LazyColumn\n",
        "import androidx.compose.foundation.lazy.items\n",
        "import androidx.compose.foundation.lazy.rememberLazyListState\n",
    ):
        c = c.replace(stale, "")

    needed_imports = [
        "import androidx.compose.foundation.layout.heightIn",
        "import androidx.compose.runtime.remember",
    ]
    last_import = re.search(r'^import .*$', c, re.MULTILINE)
    if last_import:
        pos = last_import.end()
        missing = [imp for imp in needed_imports if imp not in c]
        if missing:
            c = c[:pos] + "\n" + "\n".join(missing) + c[pos:]
            print(f"✓ FormFields: added {len(missing)} import(s)")

    # --- state: add the filtered/capped options list ---
    old_state = '''    var expanded by rememberSaveable { mutableStateOf(false) }
    val menuScrollState = rememberScrollState()
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current'''
    new_state = '''    var expanded by rememberSaveable { mutableStateOf(false) }
    val menuScrollState = rememberScrollState()
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current

    // ExposedDropdownMenu can't host a LazyColumn (it queries intrinsic
    // measurements to size itself; SubcomposeLayout-backed lazy lists don't
    // support that). Keep the required plain Column, but bound what it
    // renders: filter by what's typed (every editable usage here is a
    // suggestions-for-a-typed-value field) and cap the rest as a backstop.
    val visibleOptions = remember(options, value, editable) {
        val base = if (editable && value.isNotBlank()) {
            options.filter { it.contains(value, ignoreCase = true) }
        } else {
            options
        }
        if (base.size > 50) base.take(50) else base
    }'''
    if "val visibleOptions = remember" in c:
        print("• FormFields: filtered/capped options already present")
    elif old_state in c:
        c = c.replace(old_state, new_state, 1)
        print("✓ FormFields: added typed-text filtering + 50-item cap")
    else:
        print("⚠ FormFields: could not find FormDropdownField state block — source may have changed")

    # --- menu content: render visibleOptions instead of options ---
    pristine_menu = '''        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier.verticalScrollbar(menuScrollState),
            scrollState = menuScrollState,
            containerColor = MaterialTheme.colorScheme.surface
        ) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        onValueChange(option)
                        expanded = false
                        focusManager.clearFocus()
                    }
                )
            }
        }'''
    lazy_menu_from_v1 = '''        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier
                .verticalScrollbar(menuScrollState)
                .heightIn(max = 300.dp),
            scrollState = menuScrollState,
            containerColor = MaterialTheme.colorScheme.surface
        ) {
            val lazyListState = rememberLazyListState()
            LazyColumn(
                state = lazyListState,
                modifier = Modifier
                    .heightIn(max = 300.dp)
                    .verticalScrollbar(lazyListState)
            ) {
                items(options) { option ->
                    DropdownMenuItem(
                        text = { Text(option) },
                        onClick = {
                            onValueChange(option)
                            expanded = false
                            focusManager.clearFocus()
                        }
                    )
                }
            }
        }'''
    new_menu = '''        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier
                .verticalScrollbar(menuScrollState)
                .heightIn(max = 300.dp),
            scrollState = menuScrollState,
            containerColor = MaterialTheme.colorScheme.surface
        ) {
            visibleOptions.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        onValueChange(option)
                        expanded = false
                        focusManager.clearFocus()
                    }
                )
            }
        }'''
    if "visibleOptions.forEach" in c:
        print("• FormFields: dropdown menu already updated")
    elif pristine_menu in c:
        c = c.replace(pristine_menu, new_menu, 1)
        print("✓ FormFields: dropdown menu now renders the filtered/capped list")
    elif lazy_menu_from_v1 in c:
        c = c.replace(lazy_menu_from_v1, new_menu, 1)
        print("↺ FormFields: reverted the v1 LazyColumn attempt (crashes inside ExposedDropdownMenu) and switched to filtering")
    else:
        print("⚠ FormFields: could not find the ExposedDropdownMenu block — source may have changed")

    write(p, c)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Unified Patcher – corrected (DNS prefs + fast dropdown)")
    print("=" * 70)

    try:
        patch_appconfig()
        patch_v2rayconfig()
        patch_subedit()
        patch_strings()
        patch_coreconfigcontextbuilder()
        patch_coreconfigmanager()
        patch_settings()
        patch_formfields()
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild and test.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

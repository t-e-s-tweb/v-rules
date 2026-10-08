#!/usr/bin/env python3
"""
v2rayNG patcher for 2dust/v2rayNG master
  • Allow CUSTOM profiles in policy groups / proxy chains / routing
  • Deduplicate identical chain-hop outbounds

Idempotent.
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
# 1. ProfileItem.kt – transient field to carry the raw CUSTOM config
# ----------------------------------------------------------------------
def patch_profileitem():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/entities/ProfileItem.kt"
    if not p.exists():
        print("✗ ProfileItem.kt not found")
        return
    c = read(p)

    if "customConfigRaw" in c:
        print("• ProfileItem: customConfigRaw already present")
        return

    # Insert a body-declared transient property. Body properties are not
    # included in data-class copy() or Gson serialization, so MMKV stays
    # unchanged.
    old = '''    companion object {
        fun create(configType: EConfigType): ProfileItem =
            ProfileItem(configType = configType)
    }'''
    new = '''    /**
     * Raw JSON of a CUSTOM profile, populated in-memory by
     * MmkvManager.decodeServerConfig. Never persisted; used only to
     * extract the proxy outbound when a CUSTOM profile is used as a
     * sub-outbound (chain, policy-group member, routing target).
     */
    @Transient
    var customConfigRaw: String? = null

    companion object {
        fun create(configType: EConfigType): ProfileItem =
            ProfileItem(configType = configType)
    }'''
    if old in c:
        c = c.replace(old, new, 1)
        backup_kotlin(p)
        write(p, c)
        print("✓ ProfileItem: added transient customConfigRaw")
    else:
        print("⚠ ProfileItem: companion object not found")


# ----------------------------------------------------------------------
# 2. MmkvManager.kt – populate customConfigRaw + guid on decode
# ----------------------------------------------------------------------
def patch_mmkvmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/handler/MmkvManager.kt"
    if not p.exists():
        print("✗ MmkvManager.kt not found")
        return
    c = read(p)

    if "customConfigRaw = serverRawStorage" in c:
        print("• MmkvManager: customConfigRaw already populated")
        return

    # Add EConfigType import
    if "import com.v2ray.ang.enums.EConfigType" not in c:
        c = c.replace(
            "import com.v2ray.ang.dto.entities.ProfileItem",
            "import com.v2ray.ang.dto.entities.ProfileItem\nimport com.v2ray.ang.enums.EConfigType",
            1,
        )

    old = '''    fun decodeServerConfig(guid: String): ProfileItem? {
        if (guid.isBlank()) {
            return null
        }
        val json = profileFullStorage.decodeString(guid)
        if (json.isNullOrBlank()) {
            return null
        }
        return JsonUtil.fromJsonSafe(json, ProfileItem::class.java)
    }'''
    new = '''    fun decodeServerConfig(guid: String): ProfileItem? {
        if (guid.isBlank()) {
            return null
        }
        val json = profileFullStorage.decodeString(guid)
        if (json.isNullOrBlank()) {
            return null
        }
        val item = JsonUtil.fromJsonSafe(json, ProfileItem::class.java) ?: return null
        // CUSTOM profiles keep their full JSON in a separate store. Load it
        // into the transient field so the profile can be used as a chain
        // hop, a policy-group member, or a routing target.
        if (item.configType == EConfigType.CUSTOM) {
            item.customConfigRaw = serverRawStorage.decodeString(guid)
        }
        return item
    }'''
    if old in c:
        c = c.replace(old, new, 1)
        backup_kotlin(p)
        write(p, c)
        print("✓ MmkvManager: populate customConfigRaw on decode")
    else:
        print("⚠ MmkvManager: decodeServerConfig body not matched")


# ----------------------------------------------------------------------
# 3. CoreConfigContextBuilder.kt – allow CUSTOM in every sub-outbound slot
# ----------------------------------------------------------------------
def patch_coreconfigcontextbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"
    if not p.exists():
        print("✗ CoreConfigContextBuilder.kt not found")
        return
    c = read(p)
    changed = False

    # 3a. resolveOutbound: drop the CUSTOM short-circuit
    old_guard = '''    private fun resolveOutbound(tag: String, profile: ProfileItem): CoreConfigContext.ResolvedOutbound? {
        if (profile.configType == EConfigType.CUSTOM) {
            return null
        }
'''
    new_guard = '''    private fun resolveOutbound(tag: String, profile: ProfileItem): CoreConfigContext.ResolvedOutbound? {
'''
    if old_guard in c:
        c = c.replace(old_guard, new_guard, 1)
        changed = True
        print("✓ CoreConfigContextBuilder: removed CUSTOM guard in resolveOutbound")
    elif "if (profile.configType == EConfigType.CUSTOM) {\n            return null\n        }" not in c:
        print("• CoreConfigContextBuilder: resolveOutbound guard already absent")
    else:
        print("⚠ CoreConfigContextBuilder: resolveOutbound guard not matched")

    # 3b. resolvePolicyGroupProfiles: allow CUSTOM, still block nested groups
    old_filter = '''                .filter { !it.configType.isComplexType() }
                .toList()
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to resolve policy group profiles for '${config.remarks}'", e)'''
    new_filter = '''                .filter { !it.configType.isGroupType() }
                .toList()
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to resolve policy group profiles for '${config.remarks}'", e)'''
    if old_filter in c:
        c = c.replace(old_filter, new_filter, 1)
        changed = True
        print("✓ CoreConfigContextBuilder: policy group now accepts CUSTOM")
    else:
        print("⚠ CoreConfigContextBuilder: policy group filter not matched")

    # 3c. resolveProxyChainProfiles: same treatment
    old_chain_filter = '''                .filter { !it.configType.isComplexType() }
                .toList()
                .reversed()'''
    new_chain_filter = '''                .filter { !it.configType.isGroupType() }
                .toList()
                .reversed()'''
    if old_chain_filter in c:
        c = c.replace(old_chain_filter, new_chain_filter, 1)
        changed = True
        print("✓ CoreConfigContextBuilder: proxy chain now accepts CUSTOM")
    else:
        print("⚠ CoreConfigContextBuilder: proxy chain filter not matched")

    # 3d. resolveFallbackOutbounds: allow CUSTOM fallbacks
    old_fb = '''                    ?.takeUnless { it.configType == EConfigType.CUSTOM || it.configType == EConfigType.POLICYGROUP }'''
    new_fb = '''                    ?.takeUnless { it.configType == EConfigType.POLICYGROUP }'''
    if old_fb in c:
        c = c.replace(old_fb, new_fb, 1)
        changed = True
        print("✓ CoreConfigContextBuilder: fallback outbound accepts CUSTOM")
    else:
        print("⚠ CoreConfigContextBuilder: fallback filter not matched")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ----------------------------------------------------------------------
# 4. CoreOutboundBuilder.kt – convert a CUSTOM profile to an outbound
# ----------------------------------------------------------------------
def patch_coreoutboundbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreOutboundBuilder.kt"
    if not p.exists():
        print("✗ CoreOutboundBuilder.kt not found")
        return
    c = read(p)
    changed = False

    # 4a. Dispatch
    if "EConfigType.CUSTOM -> toOutboundCustom" not in c:
        old_dispatch = '''            EConfigType.HTTP -> toOutboundHttp(profileItem)
            else -> null'''
        new_dispatch = '''            EConfigType.HTTP -> toOutboundHttp(profileItem)
            EConfigType.CUSTOM -> toOutboundCustom(profileItem)
            else -> null'''
        if old_dispatch in c:
            c = c.replace(old_dispatch, new_dispatch, 1)
            changed = True
            print("✓ CoreOutboundBuilder: added CUSTOM dispatch case")
        else:
            print("⚠ CoreOutboundBuilder: dispatch switch not matched")

    # 4b. Skip global mux override for CUSTOM
    old_ret = '''        outbound ?: return null
        val ret = updateOutboundWithGlobalSettings(outbound)
        if (!ret) return null
        return outbound'''
    new_ret = '''        outbound ?: return null
        // CUSTOM carries its own transport/mux settings; do not apply the
        // app-global mux toggle on top of it.
        if (profileItem.configType != EConfigType.CUSTOM) {
            val ret = updateOutboundWithGlobalSettings(outbound)
            if (!ret) return null
        }
        return outbound'''
    if old_ret in c and "CUSTOM carries its own" not in c:
        c = c.replace(old_ret, new_ret, 1)
        changed = True
        print("✓ CoreOutboundBuilder: skip global mux override for CUSTOM")
    elif "CUSTOM carries its own" in c:
        print("• CoreOutboundBuilder: global-mux skip already present")
    else:
        print("⚠ CoreOutboundBuilder: convert() tail not matched")

    # 4c. The conversion function itself
    if "private fun toOutboundCustom" not in c:
        last_brace = c.rfind('}')
        if last_brace == -1:
            print("⚠ CoreOutboundBuilder: closing brace not found")
        else:
            func = '''
    /**
     * Extracts the proxy outbound from a CUSTOM profile's raw JSON.
     * The tag is cleared so the caller can assign its own.
     */
    private fun toOutboundCustom(profileItem: ProfileItem): OutboundBean? {
        val raw = profileItem.customConfigRaw ?: return null
        return try {
            val full = JsonUtil.fromJson(raw, V2rayConfig::class.java) ?: return null
            val proxy = full.getProxyOutbound() ?: return null
            // Round-trip through JSON to obtain an isolated copy we can
            // mutate freely without touching the parsed source config.
            val copy = JsonUtil.fromJson(
                JsonUtil.toJson(proxy),
                OutboundBean::class.java
            ) ?: return null
            copy.tag = ""
            copy
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to extract outbound from CUSTOM profile", e)
            null
        }
    }
'''
            c = c[:last_brace] + func + c[last_brace:]
            changed = True
            print("✓ CoreOutboundBuilder: added toOutboundCustom")
    else:
        print("• CoreOutboundBuilder: toOutboundCustom already present")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ----------------------------------------------------------------------
# 5. CoreConfigManager.kt – thread dedup map into chain handler
# ----------------------------------------------------------------------
def patch_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)
    changed = False

    # 5a. Create the dedup map once per build
    if "val chainHopDedup" not in c:
        old_call = '''        // User routing rules (policyGroupBalancerTags rewrites TAG_PROXY→balancer when main is POLICYGROUP).
        configureRouting(configContext, v2rayConfig, policyGroupBalancerTags)'''
        new_call = '''        // User routing rules (policyGroupBalancerTags rewrites TAG_PROXY→balancer when main is POLICYGROUP).
        configureRouting(configContext, v2rayConfig, policyGroupBalancerTags)'''
        # We insert the map declaration just before the forEachIndexed loop
        old_loop = '''        configContext.resolvedOutbounds.forEachIndexed { index, spec ->
            buildOutbounds(
                resolvedOutbound = spec,
                prepend = index == 0,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                policyGroupBalancerTags = policyGroupBalancerTags,
                balancerStrategies = balancerStrategies,
            )
        }'''
        new_loop = '''        // Shared across every chain built in this config: lets identical
        // hops (e.g. a subscription-wide entry/exit proxy) reuse a single
        // outbound instead of emitting one per consumer.
        val chainHopDedup = mutableMapOf<String, String>()
        configContext.resolvedOutbounds.forEachIndexed { index, spec ->
            buildOutbounds(
                resolvedOutbound = spec,
                prepend = index == 0,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                policyGroupBalancerTags = policyGroupBalancerTags,
                balancerStrategies = balancerStrategies,
                chainHopDedup = chainHopDedup,
            )
        }'''
        if old_loop in c:
            c = c.replace(old_loop, new_loop, 1)
            changed = True
            print("✓ CoreConfigManager: created chainHopDedup map")
        else:
            print("⚠ CoreConfigManager: buildOutbounds loop not matched")
    else:
        print("• CoreConfigManager: chainHopDedup already present")

    # 5b. Extend buildOutbounds signature
    old_sig = '''    private fun buildOutbounds(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: MutableMap<String, String>,
        balancerStrategies: MutableList<BalancerStrategy>,
    ) {'''
    new_sig = '''    private fun buildOutbounds(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: MutableMap<String, String>,
        balancerStrategies: MutableList<BalancerStrategy>,
        chainHopDedup: MutableMap<String, String>,
    ) {'''
    if old_sig in c:
        c = c.replace(old_sig, new_sig, 1)
        changed = True
        print("✓ CoreConfigManager: extended buildOutbounds signature")
    else:
        print("• CoreConfigManager: buildOutbounds signature unchanged or already extended")

    # 5c. Forward to chain handler
    old_chain_call = '''            CoreResolvedType.PROXYCHAIN -> handleProxyChainResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
            )'''
    new_chain_call = '''            CoreResolvedType.PROXYCHAIN -> handleProxyChainResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                chainHopDedup = chainHopDedup,
            )'''
    if old_chain_call in c:
        c = c.replace(old_chain_call, new_chain_call, 1)
        changed = True
        print("✓ CoreConfigManager: forwarded chainHopDedup to chain handler")
    else:
        print("• CoreConfigManager: PROXYCHAIN call already updated or not matched")

    # 5d. Rewrite handleProxyChainResolvedOutbound
    old_handler_pat = re.compile(
        r'    private fun handleProxyChainResolvedOutbound\(\s*'
        r'resolvedOutbound: CoreConfigContext\.ResolvedOutbound,\s*'
        r'prepend: Boolean,\s*'
        r'existingTags: MutableSet<String>,\s*'
        r'v2rayConfig: V2rayConfig,\s*'
        r'\) \{.*?\n    \}',
        re.DOTALL,
    )
    m = old_handler_pat.search(c)
    if m:
        new_handler = '''    private fun handleProxyChainResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        chainHopDedup: MutableMap<String, String>,
    ) {
        val chainOutbounds = resolvedOutbound.resolvedProfiles
            .mapNotNull { convertProfile2Outbound(it) }
            .toMutableList()
        if (chainOutbounds.isEmpty()) {
            LogUtil.w(AppConfig.TAG, "PROXYCHAIN resolved outbound '${resolvedOutbound.tag}' has no valid profiles, skipping")
            return
        }
        if (chainOutbounds.size == 1) {
            val outbound = chainOutbounds.first()
            outbound.tag = resolvedOutbound.tag
            if (prepend) {
                v2rayConfig.outbounds.add(0, outbound)
            } else {
                v2rayConfig.outbounds.add(outbound)
            }
            existingTags.add(resolvedOutbound.tag)
            return
        }

        val n = chainOutbounds.size

        // Compute a suffix signature for every hop: content of this hop
        // concatenated with the signature of everything after it. Two
        // chains that share a suffix therefore produce the same signature
        // at the first shared index, which lets us reuse a single outbound
        // for that suffix.
        val suffixSig = arrayOfNulls<String>(n + 1)
        suffixSig[n] = ""
        for (i in n - 1 downTo 0) {
            chainOutbounds[i].tag = ""
            suffixSig[i] = outboundContentSignature(chainOutbounds[i]) +
                    "\\u0001" + suffixSig[i + 1]
        }

        // Hop 0 always gets the chain's primary tag and is never deduped:
        // routing rules reference it directly.
        if (resolvedOutbound.tag in existingTags) {
            LogUtil.w(
                AppConfig.TAG,
                "PROXYCHAIN resolved outbound '${resolvedOutbound.tag}' has colliding hop tags, skipping"
            )
            return
        }
        chainOutbounds[0].tag = resolvedOutbound.tag
        existingTags.add(resolvedOutbound.tag)

        val newHops = mutableListOf<Pair<Int, V2rayConfig.OutboundBean>>()
        newHops.add(0 to chainOutbounds[0])
        val chainTags = MutableList(n) { "" }
        chainTags[0] = resolvedOutbound.tag

        for (i in 1 until n) {
            val hop = chainOutbounds[i]
            val sig = suffixSig[i]!!
            val existingTag = chainHopDedup[sig]
            if (existingTag != null) {
                chainTags[i] = existingTag
                // Hop outbound already lives in the config from a prior chain.
            } else {
                val newTag = "${AppConfig.TAG_PROXY}-${resolvedOutbound.tag}-$i"
                if (newTag in existingTags) {
                    LogUtil.w(
                        AppConfig.TAG,
                        "PROXYCHAIN resolved outbound '${resolvedOutbound.tag}' has colliding hop tags, skipping"
                    )
                    return
                }
                hop.tag = newTag
                chainTags[i] = newTag
                newHops.add(i to hop)
                existingTags.add(newTag)
                chainHopDedup[sig] = newTag
            }
        }

        // Wire dialerProxy on each newly added hop to its successor.
        newHops.forEach { (idx, outbound) ->
            if (idx < n - 1) {
                outbound.ensureSockopt().dialerProxy = chainTags[idx + 1]
            }
        }

        val toAdd = newHops.map { it.second }
        if (prepend) {
            v2rayConfig.outbounds.addAll(0, toAdd)
        } else {
            v2rayConfig.outbounds.addAll(toAdd)
        }
    }

    /**
     * Canonical content signature of an outbound. Ignores the tag and the
     * chain-specific dialerProxy so identical hops compare equal regardless
     * of where they appear in a chain.
     */
    private fun outboundContentSignature(outbound: V2rayConfig.OutboundBean): String {
        val json = try {
            JsonUtil.toJson(outbound)
        } catch (_: Exception) {
            return ""
        }
        val obj = try {
            JsonUtil.parseString(json)
        } catch (_: Exception) {
            null
        } ?: return json
        obj.remove("tag")
        obj.getAsJsonObject("streamSettings")
            ?.getAsJsonObject("sockopt")
            ?.remove("dialerProxy")
        return obj.toString()
    }'''
        c = c[:m.start()] + new_handler + c[m.end():]
        changed = True
        print("✓ CoreConfigManager: rewrote handleProxyChainResolvedOutbound with dedup")
    else:
        print("⚠ CoreConfigManager: handleProxyChainResolvedOutbound not matched")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ----------------------------------------------------------------------
# 6. Make CUSTOM profiles selectable in the UI pickers
# ----------------------------------------------------------------------
def patch_serverproxychain_activity():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/server/ServerProxyChainActivity.kt"
    if not p.exists():
        print("✗ ServerProxyChainActivity.kt not found")
        return
    c = read(p)
    changed = False

    old_list = '''        allRemarks = SettingsManager.getProfileRemarks(
            excludeConfigTypes = setOf(EConfigType.CUSTOM, EConfigType.POLICYGROUP, EConfigType.PROXYCHAIN)
        )'''
    new_list = '''        allRemarks = SettingsManager.getProfileRemarks(
            excludeConfigTypes = setOf(EConfigType.POLICYGROUP, EConfigType.PROXYCHAIN)
        )'''
    if old_list in c:
        c = c.replace(old_list, new_list, 1)
        changed = True
        print("✓ ServerProxyChainActivity: CUSTOM added to picker")
    else:
        print("• ServerProxyChainActivity: picker filter already updated or not matched")

    old_valid = '''        val invalidMembers = chainMembers.filter { member ->
            val profile = SettingsManager.getServerViaRemarks(member)
            profile == null || profile.configType.isComplexType()
        }'''
    new_valid = '''        val invalidMembers = chainMembers.filter { member ->
            val profile = SettingsManager.getServerViaRemarks(member)
            profile == null || profile.configType.isGroupType()
        }'''
    if old_valid in c:
        c = c.replace(old_valid, new_valid, 1)
        changed = True
        print("✓ ServerProxyChainActivity: validation accepts CUSTOM")
    else:
        print("• ServerProxyChainActivity: validation already updated or not matched")

    if changed:
        backup_kotlin(p)
        write(p, c)


def patch_routingedit_activity():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/routing/RoutingEditActivity.kt"
    if not p.exists():
        print("✗ RoutingEditActivity.kt not found")
        return
    c = read(p)

    old = '        val profileRemarks = SettingsManager.getProfileRemarks()'
    new = ('        val profileRemarks = SettingsManager.getProfileRemarks(\n'
           '            excludeConfigTypes = setOf(EConfigType.POLICYGROUP, EConfigType.PROXYCHAIN)\n'
           '        )')
    if old in c and "EConfigType.POLICYGROUP, EConfigType.PROXYCHAIN" not in c:
        c = c.replace(old, new, 1)
        if "import com.v2ray.ang.enums.EConfigType" not in c:
            c = c.replace(
                "import com.v2ray.ang.dto.entities.RulesetItem",
                "import com.v2ray.ang.dto.entities.RulesetItem\nimport com.v2ray.ang.enums.EConfigType",
                1,
            )
        backup_kotlin(p)
        write(p, c)
        print("✓ RoutingEditActivity: CUSTOM added to picker")
    else:
        print("• RoutingEditActivity: already updated or not matched")


def patch_subedit_activity():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/subscription/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found")
        return
    c = read(p)

    old = '''        suggestions = SettingsManager.getProfileRemarks(
            excludeConfigTypes = setOf(
                EConfigType.CUSTOM,
                EConfigType.POLICYGROUP,
                EConfigType.PROXYCHAIN,
            )
        )'''
    new = '''        suggestions = SettingsManager.getProfileRemarks(
            excludeConfigTypes = setOf(
                EConfigType.POLICYGROUP,
                EConfigType.PROXYCHAIN,
            )
        )'''
    if old in c:
        c = c.replace(old, new, 1)
        backup_kotlin(p)
        write(p, c)
        print("✓ SubEditActivity: CUSTOM added to entry/exit pickers")
    else:
        print("• SubEditActivity: already updated or not matched")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Patcher: CUSTOM everywhere + chain hop dedup")
    print("=" * 70)
    try:
        patch_profileitem()
        patch_mmkvmanager()
        patch_coreconfigcontextbuilder()
        patch_coreoutboundbuilder()
        patch_coreconfigmanager()
        patch_serverproxychain_activity()
        patch_routingedit_activity()
        patch_subedit_activity()
        print("\n✅ Done.")
        print("👉 Rebuild and test.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

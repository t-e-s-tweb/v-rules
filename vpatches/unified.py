#!/usr/bin/env python3
"""
Final patcher for v2rayNG – uses exact string anchors from current code.
- Adds None / [Current Server] to subscription editor.
- Adds [Current Server] resolution in proxy chains.
- Adds chain deduplication and custom outbound injection.
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
# 1. AppConfig.kt – add CURRENT_SERVER constant
# ----------------------------------------------------------------------
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    c = read(p)
    if '"__CURRENT_SERVER__"' in c:
        print("• AppConfig: CURRENT_SERVER already present")
        return
    old = '    const val TAG_BLOCKED = "block"'
    new = '    const val TAG_BLOCKED = "block"\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"'
    if old in c:
        write(p, c.replace(old, new, 1))
        print("✓ AppConfig: added CURRENT_SERVER")
    else:
        print("✗ AppConfig: insertion point not found")

# ----------------------------------------------------------------------
# 2. SubEditActivity.kt – dropdown with None / [Current Server]
# ----------------------------------------------------------------------
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found – skipping")
        return
    c = read(p)

    # 2.1 setupProfileRemarkInputs
    old1 = '''    private fun setupProfileRemarkInputs() {
        val suggestions = SettingsManager.getProfileRemarks(
            excludeConfigTypes = setOf(
                EConfigType.CUSTOM,
                EConfigType.POLICYGROUP,
                EConfigType.PROXYCHAIN,
            )
        )

        setupProfileRemarkInput(binding.etPreProfile, binding.btnPreProfileDropdown, suggestions)
        setupProfileRemarkInput(binding.etNextProfile, binding.btnNextProfileDropdown, suggestions)
    }'''
    new1 = '''    private fun setupProfileRemarkInputs() {
        val baseSuggestions = SettingsManager.getProfileRemarks(
            excludeConfigTypes = setOf(
                EConfigType.CUSTOM,
                EConfigType.POLICYGROUP,
                EConfigType.PROXYCHAIN,
            )
        )
        val suggestions = listOf("None", "[Current Server]") + baseSuggestions
        setupProfileRemarkInput(binding.etPreProfile, binding.btnPreProfileDropdown, suggestions)
        setupProfileRemarkInput(binding.etNextProfile, binding.btnNextProfileDropdown, suggestions)
    }'''
    if old1 in c:
        c = c.replace(old1, new1, 1)
        print("✓ SubEditActivity: updated setupProfileRemarkInputs")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInputs not found")

    # 2.2 setupProfileRemarkInput with item click mapping
    old2 = '''    private fun setupProfileRemarkInput(
        input: AutoCompleteTextView,
        dropdownButton: ImageButton,
        suggestions: List<String>
    ) {
        val adapter = ArrayAdapter(this, android.R.layout.simple_dropdown_item_1line, suggestions)
        input.setAdapter(adapter)
        input.threshold = 0

        dropdownButton.setOnClickListener {
            input.requestFocus()
            input.showDropDown()
        }
        input.setOnClickListener {
            input.showDropDown()
        }
    }'''
    new2 = '''    private fun setupProfileRemarkInput(
        input: AutoCompleteTextView,
        dropdownButton: ImageButton,
        suggestions: List<String>
    ) {
        val adapter = ArrayAdapter(this, android.R.layout.simple_dropdown_item_1line, suggestions)
        input.setAdapter(adapter)
        input.threshold = 0

        dropdownButton.setOnClickListener {
            input.requestFocus()
            input.showDropDown()
        }
        input.setOnClickListener {
            input.showDropDown()
        }

        input.setOnItemClickListener { _, _, position, _ ->
            val selected = suggestions[position]
            val stored = when (selected) {
                "None" -> ""
                "[Current Server]" -> AppConfig.CURRENT_SERVER
                else -> selected
            }
            input.setText(stored)
        }
    }'''
    if old2 in c:
        c = c.replace(old2, new2, 1)
        print("✓ SubEditActivity: updated setupProfileRemarkInput")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInput not found")

    # 2.3 bindingServer display mapping
    old3 = '''        binding.etPreProfile.text = Utils.getEditable(subItem.prevProfile)
        binding.etNextProfile.text = Utils.getEditable(subItem.nextProfile)'''
    new3 = '''        val preDisplay = when (subItem.prevProfile) {
            "" -> "None"
            AppConfig.CURRENT_SERVER -> "[Current Server]"
            else -> subItem.prevProfile
        }
        binding.etPreProfile.setText(preDisplay)
        val nextDisplay = when (subItem.nextProfile) {
            "" -> "None"
            AppConfig.CURRENT_SERVER -> "[Current Server]"
            else -> subItem.nextProfile
        }
        binding.etNextProfile.setText(nextDisplay)'''
    if old3 in c:
        c = c.replace(old3, new3, 1)
        print("✓ SubEditActivity: updated bindingServer")
    else:
        print("⚠ SubEditActivity: bindingServer lines not found")

    # 2.4 saveServer storage mapping
    old4 = '''        subItem.prevProfile = binding.etPreProfile.text.toString()
        subItem.nextProfile = binding.etNextProfile.text.toString()'''
    new4 = '''        subItem.prevProfile = when (binding.etPreProfile.text.toString()) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> binding.etPreProfile.text.toString()
        }
        subItem.nextProfile = when (binding.etNextProfile.text.toString()) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> binding.etNextProfile.text.toString()
        }'''
    if old4 in c:
        c = c.replace(old4, new4, 1)
        print("✓ SubEditActivity: updated saveServer")
    else:
        print("⚠ SubEditActivity: saveServer lines not found")

    write(p, c)
    print("✓ SubEditActivity: all enhancements applied")

# ----------------------------------------------------------------------
# 3. strings.xml – add None / [Current Server]
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
    else:
        print("• strings.xml: already present")

# ----------------------------------------------------------------------
# 4. CoreConfigContextBuilder.kt – resolve [Current Server] in chain
# ----------------------------------------------------------------------
def patch_coreconfigcontextbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"
    if not p.exists():
        print("✗ CoreConfigContextBuilder.kt not found – skipping")
        return
    c = read(p)

    # Add resolveCurrentServer helper (if not present)
    if "private fun resolveCurrentServer" not in c:
        # Insert before the last '}'
        marker = "    private fun resolveProxyChainProfilesFromGroup(config: ProfileItem): List<ProfileItem> {"
        if marker not in c:
            print("✗ CoreConfigContextBuilder: anchor not found")
            return

        # Find the end of the function to insert after it? Actually we'll insert the helper after that function.
        # Simpler: insert at the end of the file before the final '}'.
        # Locate the last '}'
        last_brace = c.rfind('}')
        if last_brace == -1:
            print("✗ CoreConfigContextBuilder: no closing brace")
            return

        helper = """

    /**
     * Resolves [Current Server] placeholder to the actual selected server's remark.
     */
    private fun resolveCurrentServer(remark: String?): String? {
        if (remark == AppConfig.CURRENT_SERVER) {
            val currId = MmkvManager.getSelectServer()
            if (!currId.isNullOrEmpty()) {
                val profile = MmkvManager.decodeServerConfig(currId)
                return profile?.remarks
            }
        }
        return remark
    }"""
        c = c[:last_brace] + helper + c[last_brace:]
        print("✓ CoreConfigContextBuilder: added resolveCurrentServer")

    # Modify resolveProxyChainProfilesFromGroup to use resolveCurrentServer
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
        print("✓ CoreConfigContextBuilder: updated resolveProxyChainProfilesFromGroup to resolve [Current Server]")
    else:
        print("⚠ CoreConfigContextBuilder: resolveProxyChainProfilesFromGroup not found (maybe already patched)")

    write(p, c)

# ----------------------------------------------------------------------
# 5. CoreConfigManager.kt – chain deduplication + custom outbound injection
# ----------------------------------------------------------------------
def patch_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found – skipping")
        return
    c = read(p)

    # 5.1 Add outboundTagMap in buildUnifiedConfig
    old_build1 = '''        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val policyGroupBalancerTags = mutableMapOf<String, String>()
        val balancerStrategies = mutableListOf<BalancerStrategy>()'''
    new_build1 = '''        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val outboundTagMap = mutableMapOf<String, String>()
        val policyGroupBalancerTags = mutableMapOf<String, String>()
        val balancerStrategies = mutableListOf<BalancerStrategy>()'''
    if old_build1 not in c:
        print("✗ CoreConfigManager: could not find declarations in buildUnifiedConfig")
        return
    c = c.replace(old_build1, new_build1, 1)

    # 5.2 Add outboundTagMap parameter to buildOutbounds call
    old_build2 = '''            buildOutbounds(
                resolvedOutbound = spec,
                prepend = index == 0,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                policyGroupBalancerTags = policyGroupBalancerTags,
                balancerStrategies = balancerStrategies,
            )'''
    new_build2 = '''            buildOutbounds(
                resolvedOutbound = spec,
                prepend = index == 0,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                policyGroupBalancerTags = policyGroupBalancerTags,
                balancerStrategies = balancerStrategies,
                outboundTagMap = outboundTagMap,
            )'''
    if old_build2 not in c:
        print("✗ CoreConfigManager: could not find buildOutbounds call")
        return
    c = c.replace(old_build2, new_build2, 1)

    # 5.3 Add outboundTagMap parameter to buildOutbounds signature
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
        outboundTagMap: MutableMap<String, String> = mutableMapOf(),
    ) {'''
    if old_sig not in c:
        print("✗ CoreConfigManager: could not find buildOutbounds signature")
        return
    c = c.replace(old_sig, new_sig, 1)

    # 5.4 Pass outboundTagMap to handleProxyChainResolvedOutbound call
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
                outboundTagMap = outboundTagMap,
            )'''
    if old_chain_call not in c:
        print("✗ CoreConfigManager: could not find PROXYCHAIN call")
        return
    c = c.replace(old_chain_call, new_chain_call, 1)

    # 5.5 Replace handleProxyChainResolvedOutbound with deduplicating version
    old_chain_func = '''    /**
     * Build and insert a multi-hop chain entry.
     */
    private fun handleProxyChainResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
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

        val chainTags = chainOutbounds.mapIndexed { index, _ ->
            if (index == 0) {
                resolvedOutbound.tag
            } else {
                "${AppConfig.TAG_PROXY}-${resolvedOutbound.tag}-$index"
            }
        }
        if (chainTags.any { it in existingTags }) {
            LogUtil.w(
                AppConfig.TAG,
                "PROXYCHAIN resolved outbound '${resolvedOutbound.tag}' has colliding hop tags, skipping"
            )
            return
        }

        chainOutbounds.forEachIndexed { index, outbound ->
            outbound.tag = chainTags[index]
        }
        for (i in 0 until chainOutbounds.size - 1) {
            chainOutbounds[i].ensureSockopt().dialerProxy = chainOutbounds[i + 1].tag
        }

        if (prepend) {
            v2rayConfig.outbounds.addAll(0, chainOutbounds)
        } else {
            v2rayConfig.outbounds.addAll(chainOutbounds)
        }
        chainOutbounds.forEach { existingTags.add(it.tag) }
    }'''
    new_chain_func = '''    /**
     * Build and insert a multi-hop chain entry.
     * Reuses existing outbounds when the same profile appears in multiple chains.
     */
    private fun handleProxyChainResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        outboundTagMap: MutableMap<String, String>,
    ) {
        val chainOutboundsWithProfiles = resolvedOutbound.resolvedProfiles
            .mapNotNull { profile -> convertProfile2Outbound(profile)?.let { profile to it } }
            .toMutableList()
        if (chainOutboundsWithProfiles.isEmpty()) {
            LogUtil.w(AppConfig.TAG, "PROXYCHAIN resolved outbound '${resolvedOutbound.tag}' has no valid profiles, skipping")
            return
        }
        if (chainOutboundsWithProfiles.size == 1) {
            val (_, outbound) = chainOutboundsWithProfiles.first()
            outbound.tag = resolvedOutbound.tag
            if (prepend) {
                v2rayConfig.outbounds.add(0, outbound)
            } else {
                v2rayConfig.outbounds.add(outbound)
            }
            existingTags.add(resolvedOutbound.tag)
            return
        }

        val chainTags = chainOutboundsWithProfiles.mapIndexed { index, (profile, _) ->
            if (index == 0) {
                resolvedOutbound.tag
            } else {
                val dedupKey = "chain-${profile.remarks}"
                outboundTagMap[dedupKey]?.let { return@mapIndexed it }
                val tag = "${AppConfig.TAG_PROXY}-${resolvedOutbound.tag}-$index"
                outboundTagMap[dedupKey] = tag
                tag
            }
        }

        chainOutboundsWithProfiles.forEachIndexed { index, (_, outbound) ->
            val tag = chainTags[index]
            outbound.tag = tag
            if (tag in existingTags) {
                return@forEachIndexed
            }
            if (prepend) {
                v2rayConfig.outbounds.add(0, outbound)
            } else {
                v2rayConfig.outbounds.add(outbound)
            }
            existingTags.add(tag)
        }

        for (i in 0 until chainTags.size - 1) {
            val currentTag = chainTags[i]
            val nextTag = chainTags[i + 1]
            v2rayConfig.outbounds.firstOrNull { it.tag == currentTag }?.ensureSockopt()?.dialerProxy = nextTag
        }
    }'''
    if old_chain_func not in c:
        print("✗ CoreConfigManager: could not find handleProxyChainResolvedOutbound")
        return
    c = c.replace(old_chain_func, new_chain_func, 1)

    # 5.6 Add helper functions (resolveCurrentServer, applySubscriptionChain, injectCustomOutbounds)
    if "private fun injectCustomOutbounds" not in c:
        anchor = "    //endregion"
        if anchor not in c:
            print("✗ CoreConfigManager: anchor '    //endregion' not found")
            return

        helpers = """
    // ------------------------------------------------------------------
    // Custom outbound injection with chain proxy support
    // ------------------------------------------------------------------

    /**
     * Resolves [Current Server] placeholder to the actual selected server's remark.
     */
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

    /**
     * Applies subscription chain (prev/next proxy) to a custom outbound.
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

            val existingByTag = v2rayConfig.outbounds.firstOrNull { it.tag == desiredTag }
            if (existingByTag != null) {
                chainTo(existingByTag)
                outboundTagMap["$chainType-$targetRemark"] = desiredTag
                LogUtil.d(AppConfig.TAG, "Reused existing $chainType outbound: $desiredTag")
                return
            }

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

            val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return
            val mainRemarks = MmkvManager.getSelectServer()?.let { MmkvManager.decodeServerConfig(it)?.remarks }
            if (chainProfile.remarks == mainRemarks) {
                outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                LogUtil.d(AppConfig.TAG, "Chain $chainType proxy is main server, set dialerProxy to proxy")
                return
            }

            val chainOutbound = convertProfile2Outbound(chainProfile) ?: return
            chainOutbound.tag = desiredTag
            outboundTagMap[mapKey] = desiredTag

            chainTo(chainOutbound)
            v2rayConfig.outbounds.add(chainOutbound)
            existingTags.add(desiredTag)
            LogUtil.d(AppConfig.TAG, "Created $chainType outbound: $desiredTag")
        }

        addChainOutbound(resolveCurrentServer(subItem.prevProfile), "prev", "$originalTag-prev") { prevOutbound ->
            outbound.ensureSockopt().dialerProxy = prevOutbound.tag
        }

        if (!subItem.nextProfile.isNullOrEmpty()) {
            val newOriginalTag = "$originalTag-orig"
            outbound.tag = newOriginalTag

            addChainOutbound(resolveCurrentServer(subItem.nextProfile), "next", originalTag) { nextOutbound ->
                nextOutbound.ensureSockopt().dialerProxy = newOriginalTag
            }
        }
    }

    /**
     * Injects custom outbounds referenced by routing rules that are not built-in.
     * Also applies prev/next chaining if the profile belongs to a subscription.
     */
    private fun injectCustomOutbounds(v2rayConfig: V2rayConfig) {
        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val outboundTagMap = mutableMapOf<String, String>()

        val rulesetItems = MmkvManager.decodeRoutingRulesets() ?: return
        val customOutboundTags = rulesetItems
            .filter { it.enabled && !AppConfig.BUILTIN_OUTBOUND_TAGS.contains(it.outboundTag) }
            .map { it.outboundTag }
            .distinct()

        for (tag in customOutboundTags) {
            if (tag in existingTags) continue
            val profile = SettingsManager.getServerViaRemarks(tag) ?: continue
            val outbound = convertProfile2Outbound(profile) ?: continue
            outbound.tag = tag

            applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)

            v2rayConfig.outbounds.add(outbound)
            existingTags.add(tag)
            outboundTagMap[tag] = tag
            LogUtil.d(AppConfig.TAG, "Injected custom outbound: $tag")
        }
    }
"""
        c = c.replace(anchor, helpers + "\n\n" + anchor, 1)
        print("✓ CoreConfigManager: added helper functions (resolveCurrentServer, applySubscriptionChain, injectCustomOutbounds)")

    # 5.7 Insert call to injectCustomOutbounds inside buildUnifiedConfig
    if "injectCustomOutbounds(v2rayConfig)" not in c:
        marker = "        // User routing rules (policyGroupBalancerTags rewrites TAG_PROXY→balancer when main is POLICYGROUP)."
        if marker in c:
            c = c.replace(marker, "        // Inject custom outbounds for routing rules\n        injectCustomOutbounds(v2rayConfig)\n\n        " + marker, 1)
            print("✓ CoreConfigManager: added injectCustomOutbounds call before user routing rules")
        else:
            # Fallback: insert before configureRouting
            fallback = "        configureRouting(configContext, v2rayConfig, policyGroupBalancerTags)"
            if fallback in c:
                c = c.replace(fallback, "        // Inject custom outbounds for routing rules\n        injectCustomOutbounds(v2rayConfig)\n\n        " + fallback, 1)
                print("✓ CoreConfigManager: added injectCustomOutbounds call before configureRouting (fallback)")
            else:
                print("⚠ CoreConfigManager: could not find insertion point for injectCustomOutbounds call")

    write(p, c)
    print("✓ CoreConfigManager: patched successfully")

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Final Patcher – uses exact anchors from current codebase")
    print("=" * 70)

    # Backup files that will be modified
    for f in [
        BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt",
        BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt",
        BASE / "app/src/main/res/values/strings.xml",
        BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt",
        BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt",
    ]:
        if f.exists():
            backup_kotlin(f)

    try:
        patch_appconfig()
        patch_subedit()
        patch_strings()
        patch_coreconfigcontextbuilder()
        patch_coreconfigmanager()
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild and test – None / [Current Server] in dropdown, custom outbounds with chaining and deduplication work.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

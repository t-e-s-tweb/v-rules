#!/usr/bin/env python3
"""
v2rayNG patcher – stable-base, no-backup version.
- Idempotent: safe to run multiple times.
- count=1 on every replacement.
- Adds CURRENT_SERVER support + chain-hop deduplication.
"""

import re
import sys
from pathlib import Path

BASE = Path("V2rayNG")

def read(p): return p.read_text(encoding="utf-8")
def write(p, s): p.write_text(s, encoding="utf-8")

def main():
    print("=" * 70)
    print("v2rayNG Patcher (Stable Base – No Backups)")
    print("=" * 70)

    # ── Pre-flight: CoreConfigManager must be clean ──
    ccm_path = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if ccm_path.exists():
        ccm = read(ccm_path)
        if "injectCustomOutbounds" in ccm or "applySubscriptionChain" in ccm:
            print("\n❌ CoreConfigManager.kt still contains old-patch artifacts!")
            print("   Restore it from your clean base before running this script.")
            sys.exit(1)

    patch_appconfig()
    patch_subedit()
    patch_strings()
    patch_coreconfig_context_builder()
    patch_coreconfig_manager()

    print("\n✅ All patches applied successfully.")
    print("   Build with: ./gradlew assembleFdroidRelease")

# ─────────────────────────────────────────────────────────────────────────
# 1. AppConfig.kt
# ─────────────────────────────────────────────────────────────────────────
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    c = read(p)
    if "CURRENT_SERVER" in c:
        print("• AppConfig: CURRENT_SERVER already present")
        return
    old = '    const val TAG_BLOCKED = "block"'
    new = '    const val TAG_BLOCKED = "block"\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"'
    if old in c:
        write(p, c.replace(old, new, 1))
        print("✓ AppConfig: added CURRENT_SERVER")
    else:
        print("✗ AppConfig: insertion point not found")

# ─────────────────────────────────────────────────────────────────────────
# 2. SubEditActivity.kt
# ─────────────────────────────────────────────────────────────────────────
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found")
        return
    c = read(p)

    # 2.1 setupProfileRemarkInputs
    old = '''    private fun setupProfileRemarkInputs() {
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
    new = '''    private fun setupProfileRemarkInputs() {
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
    if old in c:
        c = c.replace(old, new, 1)
        print("✓ SubEditActivity: updated setupProfileRemarkInputs")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInputs not found")

    # 2.2 setupProfileRemarkInput
    old = '''    private fun setupProfileRemarkInput(
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
    new = '''    private fun setupProfileRemarkInput(
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
    if old in c:
        c = c.replace(old, new, 1)
        print("✓ SubEditActivity: updated setupProfileRemarkInput")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInput not found")

    # 2.3 bindingServer display mapping
    old = '''        binding.etPreProfile.text = Utils.getEditable(subItem.prevProfile)
        binding.etNextProfile.text = Utils.getEditable(subItem.nextProfile)'''
    new = '''        val preDisplay = when (subItem.prevProfile) {
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
    if old in c:
        c = c.replace(old, new, 1)
        print("✓ SubEditActivity: updated bindingServer")
    else:
        print("⚠ SubEditActivity: bindingServer lines not found")

    # 2.4 saveServer storage mapping
    old = '''        subItem.prevProfile = binding.etPreProfile.text.toString()
        subItem.nextProfile = binding.etNextProfile.text.toString()'''
    new = '''        subItem.prevProfile = when (binding.etPreProfile.text.toString()) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> binding.etPreProfile.text.toString()
        }
        subItem.nextProfile = when (binding.etNextProfile.text.toString()) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> binding.etNextProfile.text.toString()
        }'''
    if old in c:
        c = c.replace(old, new, 1)
        print("✓ SubEditActivity: updated saveServer")
    else:
        print("⚠ SubEditActivity: saveServer lines not found")

    write(p, c)

# ─────────────────────────────────────────────────────────────────────────
# 3. strings.xml
# ─────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────
# 4. CoreConfigContextBuilder.kt – add resolveCurrentServer
# ─────────────────────────────────────────────────────────────────────────
def patch_coreconfig_context_builder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"
    if not p.exists():
        print("✗ CoreConfigContextBuilder.kt not found")
        return
    c = read(p)

    if "private fun resolveCurrentServer" in c:
        print("• CoreConfigContextBuilder: resolveCurrentServer already present")
        return

    old = '''    private fun resolveProxyChainProfilesFromGroup(config: ProfileItem): List<<ProfileItem> {
        if (config.subscriptionId.isEmpty()) {
            return listOf(config)
        }

        try {
            val subItem = MmkvManager.decodeSubscription(config.subscriptionId) ?: return listOf(config)
            val resolved = mutableListOf<<ProfileItem>()
            SettingsManager.getServerViaRemarks(subItem.nextProfile)?.let { resolved.add(it) }
            resolved.add(config)
            SettingsManager.getServerViaRemarks(subItem.prevProfile)?.let { resolved.add(it) }
            return resolved
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to resolve proxy chain from group for '${config.remarks}'", e)
            return listOf(config)
        }
    }'''

    new = '''    private fun resolveProxyChainProfilesFromGroup(config: ProfileItem): List<<ProfileItem> {
        if (config.subscriptionId.isEmpty()) {
            return listOf(config)
        }

        try {
            val subItem = MmkvManager.decodeSubscription(config.subscriptionId) ?: return listOf(config)
            val resolved = mutableListOf<<ProfileItem>()
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
    }

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
    }'''

    if old in c:
        c = c.replace(old, new, 1)
        write(p, c)
        print("✓ CoreConfigContextBuilder: added resolveCurrentServer")
    else:
        print("✗ CoreConfigContextBuilder: could not find resolveProxyChainProfilesFromGroup")

# ─────────────────────────────────────────────────────────────────────────
# 5. CoreConfigManager.kt – add chain-hop deduplication
# ─────────────────────────────────────────────────────────────────────────
def patch_coreconfig_manager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)

    if "outboundTagMap: MutableMap<String, String>" in c:
        print("• CoreConfigManager: deduplication already present")
        return

    # 5.1 Add outboundTagMap declaration in buildUnifiedConfig
    old1 = '''        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val policyGroupBalancerTags = mutableMapOf<String, String>()
        val balancerStrategies = mutableListOf<<BalancerStrategy>()'''
    new1 = '''        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val outboundTagMap = mutableMapOf<String, String>()
        val policyGroupBalancerTags = mutableMapOf<String, String>()
        val balancerStrategies = mutableListOf<<BalancerStrategy>()'''
    if old1 not in c:
        print("✗ CoreConfigManager: could not find buildUnifiedConfig declarations")
        return
    c = c.replace(old1, new1, 1)

    # 5.2 Pass outboundTagMap into buildOutbounds call
    old2 = '''            buildOutbounds(
                resolvedOutbound = spec,
                prepend = index == 0,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                policyGroupBalancerTags = policyGroupBalancerTags,
                balancerStrategies = balancerStrategies,
            )'''
    new2 = '''            buildOutbounds(
                resolvedOutbound = spec,
                prepend = index == 0,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                policyGroupBalancerTags = policyGroupBalancerTags,
                balancerStrategies = balancerStrategies,
                outboundTagMap = outboundTagMap,
            )'''
    if old2 not in c:
        print("✗ CoreConfigManager: could not find buildOutbounds call")
        return
    c = c.replace(old2, new2, 1)

    # 5.3 Add outboundTagMap parameter to buildOutbounds signature
    old3 = '''    private fun buildOutbounds(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: MutableMap<String, String>,
        balancerStrategies: MutableList<<BalancerStrategy>,
    ) {'''
    new3 = '''    private fun buildOutbounds(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: MutableMap<String, String>,
        balancerStrategies: MutableList<<BalancerStrategy>,
        outboundTagMap: MutableMap<String, String> = mutableMapOf(),
    ) {'''
    if old3 not in c:
        print("✗ CoreConfigManager: could not find buildOutbounds signature")
        return
    c = c.replace(old3, new3, 1)

    # 5.4 Pass outboundTagMap into handleProxyChainResolvedOutbound call
    old4 = '''            CoreResolvedType.PROXYCHAIN -> handleProxyChainResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
            )'''
    new4 = '''            CoreResolvedType.PROXYCHAIN -> handleProxyChainResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                outboundTagMap = outboundTagMap,
            )'''
    if old4 not in c:
        print("✗ CoreConfigManager: could not find PROXYCHAIN call")
        return
    c = c.replace(old4, new4, 1)

    # 5.5 Replace handleProxyChainResolvedOutbound body with deduplicating version
    old5 = '''    /**
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

    new5 = '''    /**
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

    if old5 not in c:
        print("✗ CoreConfigManager: could not find handleProxyChainResolvedOutbound")
        return
    c = c.replace(old5, new5, 1)

    write(p, c)
    print("✓ CoreConfigManager: added chain-hop deduplication")

if __name__ == "__main__":
    main()

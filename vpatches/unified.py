#!/usr/bin/env python3
"""
Final patcher for v2rayNG – fixes [Current Server] chain handling.
- Adds detailed logging to debug conversion failures.
- Ensures chains work even when [Current Server] is used in pre/next.
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

def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found – skipping")
        return
    c = read(p)

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
# Patched CoreConfigManager.kt with logging and fixes
# ----------------------------------------------------------------------
PATCHED_CORECONFIG_MANAGER = r'''package com.v2ray.ang.core

import android.content.Context
import android.text.TextUtils
import com.google.gson.JsonArray
import com.v2ray.ang.AppConfig
import com.v2ray.ang.dto.ConfigResult
import com.v2ray.ang.dto.CoreConfigContext
import com.v2ray.ang.dto.V2rayConfig
import com.v2ray.ang.dto.entities.ProfileItem
import com.v2ray.ang.dto.entities.RulesetItem
import com.v2ray.ang.enums.BalancerStrategyType
import com.v2ray.ang.enums.CoreResolvedType
import com.v2ray.ang.enums.EConfigType
import com.v2ray.ang.extension.isNotNullEmpty
import com.v2ray.ang.handler.MmkvManager
import com.v2ray.ang.handler.SettingsManager
import com.v2ray.ang.util.HttpUtil
import com.v2ray.ang.util.JsonUtil
import com.v2ray.ang.util.LogUtil
import com.v2ray.ang.util.PackageUidResolver
import com.v2ray.ang.util.Utils

object CoreConfigManager {
    private var initConfigCache: String? = null
    private var initConfigCacheWithTun: String? = null

    //region get config function

    fun getV2rayConfig(context: Context, guid: String): ConfigResult {
        try {
            val configContext = CoreConfigContextBuilder.build(context, guid)
                ?: return ConfigResult(status = false, guid = guid, errorMessage = "Failed to build config context")
            if (configContext.isCustom) {
                return buildV2rayCustomConfig(configContext)
            }
            return toConfigResult(configContext, buildUnifiedConfig(configContext))
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to get V2ray config", e)
            return ConfigResult(
                status = false,
                guid = guid,
                errorMessage = "Failed to get V2ray config: ${e.message ?: e.javaClass.simpleName}"
            )
        }
    }

    fun getV2rayConfig4Speedtest(context: Context, guid: String): ConfigResult {
        try {
            val configContext = CoreConfigContextBuilder.build(context, guid)
                ?: return ConfigResult(status = false, guid = guid, errorMessage = "Failed to build config context")
            if (configContext.isCustom) {
                return buildV2rayCustomConfig(configContext)
            }
            val v2rayConfig = buildUnifiedConfig(configContext)
            postProcessForSpeedtest(v2rayConfig)
            return toConfigResult(configContext, v2rayConfig)
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to get V2ray config for speedtest", e)
            return ConfigResult(
                status = false,
                guid = guid,
                errorMessage = "Failed to get V2ray config for speedtest: ${e.message ?: e.javaClass.simpleName}"
            )
        }
    }

    private fun buildV2rayCustomConfig(configContext: CoreConfigContext): ConfigResult {
        val context = configContext.context
        val raw = MmkvManager.decodeServerRaw(configContext.guid)
            ?: return ConfigResult(status = false, guid = configContext.guid, errorMessage = "Custom config is empty")
        val result = ConfigResult(true, configContext.guid, raw)
        if (!needTun()) {
            return result
        }

        val json = JsonUtil.parseString(raw)?.takeIf { it.isJsonObject }?.asJsonObject ?: return result

        if (SettingsManager.canUseProcessRouting()) {
            val rulesJson = json.get("routing")?.takeIf { it.isJsonObject }?.asJsonObject
                ?.get("rules")?.takeIf { it.isJsonArray }?.asJsonArray
                ?: JsonArray()

            for (elem in rulesJson) {
                val rule = elem.takeIf { it.isJsonObject }?.asJsonObject ?: continue
                val process = rule.get("process")?.takeIf { it.isJsonArray }?.asJsonArray ?: continue
                val packages = process.mapNotNull {
                    it.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
                }.takeIf { it.isNotEmpty() } ?: continue
                val uids = PackageUidResolver.packageNamesToUids(context, packages).takeIf { it.isNotEmpty() } ?: continue
                rule.add("process", JsonArray().apply { uids.forEach { add(it) } })
            }
        }

        val inboundsJson = json.get("inbounds")?.takeIf { it.isJsonArray }?.asJsonArray
            ?: JsonArray().also { json.add("inbounds", it) }
        val tunNotExists = inboundsJson.none { elem ->
            elem.isJsonObject && elem.asJsonObject.get("protocol")
                ?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }
                ?.asString == "tun"
        }

        if (tunNotExists) {
            val templateConfig = initV2rayConfig(configContext)
            templateConfig.inbounds.firstOrNull { it.tag == "tun" }?.let { inboundTun ->
                inboundTun.settings?.mtu = SettingsManager.getVpnMtu()
                inboundsJson.add(JsonUtil.parseString(JsonUtil.toJson(inboundTun)))
            }
        }

        return JsonUtil.toJsonPretty(json)?.let { ConfigResult(true, configContext.guid, it) } ?: result
    }

    private fun buildUnifiedConfig(configContext: CoreConfigContext): V2rayConfig {
        require(configContext.resolvedOutbounds.isNotEmpty()) { "resolvedOutbounds must not be empty for a non-CUSTOM context" }
        val primaryResolvedOutbound = configContext.resolvedOutbounds.first()

        val v2rayConfig = initV2rayConfig(configContext)
        v2rayConfig.log.loglevel = MmkvManager.decodeSettingsString(AppConfig.PREF_LOGLEVEL) ?: "warning"
        v2rayConfig.remarks = primaryResolvedOutbound.profile.remarks

        configureInbounds(v2rayConfig)

        if (v2rayConfig.outbounds.isNotEmpty()) {
            v2rayConfig.outbounds.removeAt(0)
        }
        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val outboundTagMap = mutableMapOf<String, String>()
        val policyGroupBalancerTags = mutableMapOf<String, String>()
        val balancerStrategies = mutableListOf<BalancerStrategy>()

        configContext.resolvedOutbounds.forEachIndexed { index, spec ->
            buildOutbounds(
                resolvedOutbound = spec,
                prepend = index == 0,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                policyGroupBalancerTags = policyGroupBalancerTags,
                balancerStrategies = balancerStrategies,
                outboundTagMap = outboundTagMap,
            )
        }

        injectCustomOutbounds(v2rayConfig)

        configureRouting(configContext, v2rayConfig, policyGroupBalancerTags)
        configureFakeDns(v2rayConfig)
        configureDns(v2rayConfig, policyGroupBalancerTags)
        configureLocalDns(v2rayConfig)

        if (primaryResolvedOutbound.resolvedType == CoreResolvedType.POLICYGROUP) {
            if (v2rayConfig.routing.domainStrategy == "IPIfNonMatch") {
                v2rayConfig.routing.rules.add(
                    V2rayConfig.RoutingBean.RulesBean(
                        ip = arrayListOf("0.0.0.0/0", "::/0"),
                        balancerTag = AppConfig.TAG_BALANCER,
                    )
                )
            } else {
                v2rayConfig.routing.rules.add(
                    V2rayConfig.RoutingBean.RulesBean(
                        network = "tcp,udp",
                        balancerTag = AppConfig.TAG_BALANCER,
                    )
                )
            }
        }

        applyObservability(v2rayConfig, balancerStrategies)
        applySpeedDisabled(v2rayConfig)
        resolveOutboundDomainsToHosts(v2rayConfig)

        return v2rayConfig
    }

    private fun buildOutbounds(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: MutableMap<String, String>,
        balancerStrategies: MutableList<BalancerStrategy>,
        outboundTagMap: MutableMap<String, String> = mutableMapOf(),
    ) {
        if (resolvedOutbound.tag in existingTags) {
            LogUtil.w(AppConfig.TAG, "Resolved outbound tag '${resolvedOutbound.tag}' already exists, skipping duplicated entry")
            return
        }

        when (resolvedOutbound.resolvedType) {
            CoreResolvedType.NORMAL -> handleNormalResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
            )
            CoreResolvedType.PROXYCHAIN -> handleProxyChainResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                outboundTagMap = outboundTagMap,
            )
            CoreResolvedType.POLICYGROUP -> handlePolicyGroupResolvedOutbound(
                resolvedOutbound = resolvedOutbound,
                prepend = prepend,
                existingTags = existingTags,
                v2rayConfig = v2rayConfig,
                policyGroupBalancerTags = policyGroupBalancerTags,
                balancerStrategies = balancerStrategies,
            )
        }
    }

    private fun handleNormalResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
    ) {
        val profile = resolvedOutbound.resolvedProfiles.firstOrNull() ?: run {
            LogUtil.w(AppConfig.TAG, "NORMAL resolved outbound '${resolvedOutbound.tag}' has empty resolvedProfiles, skipping")
            return
        }
        val outbound = convertProfile2Outbound(profile) ?: run {
            LogUtil.w(AppConfig.TAG, "Could not convert NORMAL resolved outbound '${resolvedOutbound.tag}' profile to outbound, skipping")
            return
        }
        outbound.tag = resolvedOutbound.tag
        if (prepend) {
            v2rayConfig.outbounds.add(0, outbound)
        } else {
            v2rayConfig.outbounds.add(outbound)
        }
        existingTags.add(resolvedOutbound.tag)
    }

    private fun handleProxyChainResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        outboundTagMap: MutableMap<String, String>,
    ) {
        LogUtil.d(AppConfig.TAG, "🔗 Processing PROXYCHAIN for tag='${resolvedOutbound.tag}', prepend=$prepend")
        LogUtil.d(AppConfig.TAG, "   Number of resolvedProfiles: ${resolvedOutbound.resolvedProfiles.size}")
        
        val chainOutboundsWithProfiles = resolvedOutbound.resolvedProfiles
            .mapNotNull { profile ->
                LogUtil.d(AppConfig.TAG, "   Converting profile: remarks='${profile.remarks}', type=${profile.configType}, server='${profile.server}'")
                val outbound = convertProfile2Outbound(profile)
                if (outbound == null) {
                    LogUtil.e(AppConfig.TAG, "   ❌ FAILED to convert profile '${profile.remarks}' (type=${profile.configType})")
                }
                outbound?.let { profile to it }
            }
            .toMutableList()
            
        LogUtil.d(AppConfig.TAG, "   Successfully converted ${chainOutboundsWithProfiles.size}/${resolvedOutbound.resolvedProfiles.size} profiles")
        
        if (chainOutboundsWithProfiles.isEmpty()) {
            LogUtil.w(AppConfig.TAG, "PROXYCHAIN resolved outbound '${resolvedOutbound.tag}' has no valid profiles, skipping")
            return
        }
        if (chainOutboundsWithProfiles.size == 1) {
            val (profile, outbound) = chainOutboundsWithProfiles.first()
            LogUtil.w(AppConfig.TAG, "⚠️ Only one profile converted: '${profile.remarks}'. Treating as single-hop (no chain)")
            outbound.tag = resolvedOutbound.tag
            if (prepend) {
                v2rayConfig.outbounds.add(0, outbound)
            } else {
                v2rayConfig.outbounds.add(outbound)
            }
            existingTags.add(resolvedOutbound.tag)
            LogUtil.d(AppConfig.TAG, "✅ Added as single-hop outbound '${resolvedOutbound.tag}'")
            return
        }

        val chainTags = chainOutboundsWithProfiles.mapIndexed { index, (profile, _) ->
            if (index == 0) {
                resolvedOutbound.tag
            } else {
                val dedupKey = "chain-${profile.remarks}"
                outboundTagMap[dedupKey]?.let {
                    LogUtil.d(AppConfig.TAG, "♻️ Reusing existing hop for '${profile.remarks}' as tag '$it'")
                    return@mapIndexed it
                }
                val tag = "${AppConfig.TAG_PROXY}-${resolvedOutbound.tag}-$index"
                outboundTagMap[dedupKey] = tag
                LogUtil.d(AppConfig.TAG, "🆕 Creating new hop tag '$tag' for '${profile.remarks}'")
                tag
            }
        }

        chainOutboundsWithProfiles.forEachIndexed { index, (_, outbound) ->
            val tag = chainTags[index]
            outbound.tag = tag
            if (tag in existingTags) {
                LogUtil.d(AppConfig.TAG, "⏩ Hop tag '$tag' already exists, skipping addition")
                return@forEachIndexed
            }
            if (prepend) {
                v2rayConfig.outbounds.add(0, outbound)
            } else {
                v2rayConfig.outbounds.add(outbound)
            }
            existingTags.add(tag)
            LogUtil.d(AppConfig.TAG, "➕ Added outbound with tag '$tag'")
        }

        for (i in 0 until chainTags.size - 1) {
            val currentTag = chainTags[i]
            val nextTag = chainTags[i + 1]
            val currentOutbound = v2rayConfig.outbounds.firstOrNull { it.tag == currentTag }
            if (currentOutbound != null) {
                currentOutbound.ensureSockopt().dialerProxy = nextTag
                LogUtil.d(AppConfig.TAG, "🔗 Set dialerProxy of '$currentTag' → '$nextTag'")
            } else {
                LogUtil.e(AppConfig.TAG, "❌ Could not find outbound with tag '$currentTag' to set dialerProxy")
            }
        }
    }

    private fun handlePolicyGroupResolvedOutbound(
        resolvedOutbound: CoreConfigContext.ResolvedOutbound,
        prepend: Boolean,
        existingTags: MutableSet<String>,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: MutableMap<String, String>,
        balancerStrategies: MutableList<BalancerStrategy>,
    ) {
        val memberPairs = resolvedOutbound.resolvedProfiles.mapNotNull { profile ->
            convertProfile2Outbound(profile)?.let { ob -> ob to profile }
        }
        if (memberPairs.isEmpty()) {
            LogUtil.w(AppConfig.TAG, "POLICYGROUP resolved outbound '${resolvedOutbound.tag}' has no valid member outbounds, skipping")
            return
        }

        val memberTagPrefix = "${AppConfig.TAG_PROXY}-${resolvedOutbound.tag}-"
        val membersToAdd = mutableListOf<V2rayConfig.OutboundBean>()
        memberPairs.forEachIndexed { index, (outbound, profile) ->
            val memberTag = "$memberTagPrefix${index + 1}-${profile.remarks.trim()}"
            if (memberTag in existingTags) {
                return@forEachIndexed
            }
            outbound.tag = memberTag
            membersToAdd.add(outbound)
            existingTags.add(memberTag)
        }

        if (membersToAdd.isEmpty()) {
            LogUtil.w(
                AppConfig.TAG,
                "POLICYGROUP resolved outbound '${resolvedOutbound.tag}' produced no unique member tags, skipping"
            )
            return
        }

        if (prepend) {
            v2rayConfig.outbounds.addAll(0, membersToAdd)
        } else {
            v2rayConfig.outbounds.addAll(membersToAdd)
        }

        val balancerTag = if (resolvedOutbound.tag == AppConfig.TAG_PROXY) {
            AppConfig.TAG_BALANCER
        } else {
            "${AppConfig.TAG_BALANCER_PRE}-${resolvedOutbound.tag}"
        }
        val strategy = buildBalancerStrategy(
            policyGroupType = resolvedOutbound.profile.policyGroupType,
            selector = listOf(memberTagPrefix),
            balancerTag = balancerTag,
        )
        val existingBalancers = v2rayConfig.routing.balancers?.toMutableList() ?: mutableListOf()
        if (existingBalancers.none { it.tag == balancerTag }) {
            existingBalancers.add(strategy.balancer)
            v2rayConfig.routing.balancers = existingBalancers
        }
        balancerStrategies.add(strategy)
        policyGroupBalancerTags[resolvedOutbound.tag] = balancerTag
    }

    private fun postProcessForSpeedtest(v2rayConfig: V2rayConfig) {
        v2rayConfig.log.loglevel = MmkvManager.decodeSettingsString(AppConfig.PREF_LOGLEVEL) ?: "warning"
        v2rayConfig.inbounds.clear()
        v2rayConfig.routing.rules.clear()
        v2rayConfig.dns = null
        v2rayConfig.fakedns = null
        v2rayConfig.stats = null
        v2rayConfig.policy = null
        v2rayConfig.outbounds.forEach { key -> key.mux = null }
    }

    private fun toConfigResult(configContext: CoreConfigContext, v2rayConfig: V2rayConfig): ConfigResult {
        return ConfigResult(
            status = true,
            guid = configContext.guid,
            content = JsonUtil.toJsonPretty(v2rayConfig) ?: ""
        )
    }

    private fun initV2rayConfig(configContext: CoreConfigContext): V2rayConfig {
        val context = configContext.context
        val assets: String
        if (needTun()) {
            assets = initConfigCacheWithTun ?: Utils.readTextFromAssets(context, "v2ray_config_with_tun.json")
            if (TextUtils.isEmpty(assets)) {
                error("Missing asset: v2ray_config_with_tun.json")
            }
            initConfigCacheWithTun = assets
        } else {
            assets = initConfigCache ?: Utils.readTextFromAssets(context, "v2ray_config.json")
            if (TextUtils.isEmpty(assets)) {
                error("Missing asset: v2ray_config.json")
            }
            initConfigCache = assets
        }
        return JsonUtil.fromJson(assets, V2rayConfig::class.java)
            ?: error("Failed to parse config template")
    }

    //endregion

    //region some sub function

    private fun needTun(): Boolean {
        return SettingsManager.isVpnMode() && !SettingsManager.isUsingHevTun()
    }

    private fun configureInbounds(v2rayConfig: V2rayConfig) {
        val vpn = SettingsManager.isVpnMode()
        val useHev = SettingsManager.isUsingHevTun()
        val forcedByHev = vpn && useHev
        val enableLocalProxy = forcedByHev || MmkvManager.decodeSettingsBool(AppConfig.PREF_ENABLE_LOCAL_PROXY, true)
        val socksPort = SettingsManager.getSocksPort()
        val socksUsername = SettingsManager.getSocksUsername()
        val socksPassword = SettingsManager.getSocksPassword()
        val inbound1 = v2rayConfig.inbounds[0]
        if (inbound1.settings == null) {
            inbound1.settings = V2rayConfig.InboundBean.InSettingsBean()
        }
        if (MmkvManager.decodeSettingsBool(AppConfig.PREF_PROXY_SHARING) != true) {
            inbound1.listen = AppConfig.LOOPBACK
        }
        inbound1.port = socksPort
        inbound1.settings?.udp = MmkvManager.decodeSettingsBool(AppConfig.PREF_SOCKS_ENABLE_UDP, true)
        if (socksUsername != null && socksPassword != null) {
            inbound1.settings?.auth = "password"
            inbound1.settings?.accounts = listOf(
                V2rayConfig.InboundBean.InSettingsBean.SocksAccountBean(
                    user = socksUsername,
                    pass = socksPassword
                )
            )
        } else {
            inbound1.settings?.auth = "noauth"
            inbound1.settings?.accounts = null
        }
        val fakedns = MmkvManager.decodeSettingsBool(AppConfig.PREF_FAKE_DNS_ENABLED) == true
        val sniffAllTlsAndHttp = MmkvManager.decodeSettingsBool(AppConfig.PREF_SNIFFING_ENABLED, true) != false
        inbound1.sniffing?.enabled = fakedns || sniffAllTlsAndHttp
        inbound1.sniffing?.routeOnly = MmkvManager.decodeSettingsBool(AppConfig.PREF_ROUTE_ONLY_ENABLED, false)
        if (!sniffAllTlsAndHttp) {
            inbound1.sniffing?.destOverride?.clear()
        }
        if (fakedns) {
            inbound1.sniffing?.destOverride?.add("fakedns")
        }
        if (!Utils.isXray()) {
            val inbound2 = JsonUtil.fromJson(JsonUtil.toJson(inbound1), V2rayConfig.InboundBean::class.java)
                ?: error("Failed to clone inbound template")
            inbound2.tag = EConfigType.HTTP.name.lowercase()
            inbound2.port = SettingsManager.getHttpPort()
            inbound2.protocol = EConfigType.HTTP.name.lowercase()
            inbound2.settings?.auth = null
            inbound2.settings?.udp = null
            v2rayConfig.inbounds.add(inbound2)
        }
        if (!enableLocalProxy) {
            v2rayConfig.inbounds.removeIf { it.protocol == "socks" || it.protocol == "http" }
        }
        if (needTun()) {
            val inboundTun = v2rayConfig.inbounds.firstOrNull { e -> e.tag == "tun" }
            inboundTun?.settings?.mtu = SettingsManager.getVpnMtu()
            inboundTun?.sniffing = inbound1.sniffing
        }
    }

    private fun configureFakeDns(v2rayConfig: V2rayConfig) {
        if (MmkvManager.decodeSettingsBool(AppConfig.PREF_LOCAL_DNS_ENABLED) == true
            && MmkvManager.decodeSettingsBool(AppConfig.PREF_FAKE_DNS_ENABLED) == true
        ) {
            v2rayConfig.fakedns = listOf(V2rayConfig.FakednsBean())
        }
    }

    private fun collectUserRuleDomainsByTag(tag: String): ArrayList<String> {
        val domain = ArrayList<String>()
        val rulesetItems = MmkvManager.decodeRoutingRulesets()
        rulesetItems?.forEach { key ->
            if (key.enabled && key.outboundTag == tag && !key.domain.isNullOrEmpty()) {
                key.domain?.forEach { domain.add(it) }
            }
        }
        return domain
    }

    private fun collectCustomOutboundDomains(): ArrayList<String> {
        val domain = ArrayList<String>()
        val rulesetItems = MmkvManager.decodeRoutingRulesets()
        rulesetItems?.forEach { key ->
            if (key.enabled && !AppConfig.BUILTIN_OUTBOUND_TAGS.contains(key.outboundTag) && !key.domain.isNullOrEmpty()) {
                key.domain?.forEach { domain.add(it) }
            }
        }
        return domain
    }

    private fun configureLocalDns(v2rayConfig: V2rayConfig) {
        if (MmkvManager.decodeSettingsBool(AppConfig.PREF_LOCAL_DNS_ENABLED) != true) return
        if (MmkvManager.decodeSettingsBool(AppConfig.PREF_FAKE_DNS_ENABLED) == true) {
            val geositeCn = arrayListOf(AppConfig.GEOSITE_CN)
            val proxyDomain = collectUserRuleDomainsByTag(AppConfig.TAG_PROXY)
            val directDomain = collectUserRuleDomainsByTag(AppConfig.TAG_DIRECT)
            val finalDomain = geositeCn.plus(proxyDomain).plus(directDomain).distinct()
            v2rayConfig.dns?.servers?.add(
                0,
                V2rayConfig.DnsBean.ServersBean(address = "fakedns", domains = finalDomain)
            )
        }
        if (SettingsManager.isVpnMode()) {
            if (SettingsManager.isUsingHevTun()) {
                v2rayConfig.routing.rules.add(
                    0, V2rayConfig.RoutingBean.RulesBean(
                        inboundTag = arrayListOf("socks"),
                        outboundTag = "dns-out",
                        port = "53",
                    )
                )
            } else {
                v2rayConfig.routing.rules.add(
                    0, V2rayConfig.RoutingBean.RulesBean(
                        inboundTag = arrayListOf("tun"),
                        outboundTag = "dns-out",
                        port = "53",
                    )
                )
            }
        }
        if (v2rayConfig.outbounds.none { e -> e.protocol == "dns" && e.tag == "dns-out" }) {
            v2rayConfig.outbounds.add(
                V2rayConfig.OutboundBean(
                    protocol = "dns",
                    tag = "dns-out",
                    settings = null,
                    streamSettings = null,
                    mux = null
                )
            )
        }
    }

    private fun applySpeedDisabled(v2rayConfig: V2rayConfig) {
        if (MmkvManager.decodeSettingsBool(AppConfig.PREF_SPEED_ENABLED) != true) {
            v2rayConfig.stats = null
            v2rayConfig.policy = null
        }
    }

    private fun configureDns(v2rayConfig: V2rayConfig, policyGroupBalancerTags: Map<String, String>) {
        val hosts = mutableMapOf<String, Any>()
        val servers = ArrayList<Any>()
        val remoteDns = SettingsManager.getRemoteDnsServers()
        val proxyDomain = (collectUserRuleDomainsByTag(AppConfig.TAG_PROXY) + collectCustomOutboundDomains()).distinct()
        remoteDns.forEach { servers.add(it) }
        if (proxyDomain.isNotEmpty()) {
            servers.add(V2rayConfig.DnsBean.ServersBean(address = remoteDns.first(), domains = proxyDomain))
        }
        val domesticDns = SettingsManager.getDomesticDnsServers()
        val directDomain = collectUserRuleDomainsByTag(AppConfig.TAG_DIRECT)
        val isCnRoutingMode = directDomain.contains(AppConfig.GEOSITE_CN)
        val cnRegionFilter = { domain: String ->
            domain.startsWith("geosite:") && (domain.endsWith("-cn") || domain.endsWith("@cn")) || domain == AppConfig.GEOSITE_CN
        }
        val finalDirectDomain = if (isCnRoutingMode) directDomain.filterNot { cnRegionFilter(it) } else directDomain
        val domesticDnsTags = mutableListOf<String>()
        domesticDns.forEachIndexed { index, element ->
            val tag = AppConfig.TAG_DOMESTIC_DNS + index
            servers.add(V2rayConfig.DnsBean.ServersBean(address = element, domains = finalDirectDomain, skipFallback = true, tag = tag))
            domesticDnsTags.add(tag)
        }
        if (isCnRoutingMode) {
            val geoipCn = arrayListOf(AppConfig.GEOIP_CN)
            val cnRegionDomain = directDomain.filter { cnRegionFilter(it) }
            domesticDns.forEachIndexed { index, element ->
                val geositeCnDnsTag = AppConfig.TAG_DOMESTIC_DNS + index + "_cn_expect"
                servers.add(V2rayConfig.DnsBean.ServersBean(address = element, domains = cnRegionDomain, expectIPs = geoipCn, skipFallback = true, tag = geositeCnDnsTag))
                domesticDnsTags.add(geositeCnDnsTag)
            }
        }
        val blkDomain = collectUserRuleDomainsByTag(AppConfig.TAG_BLOCKED)
        if (blkDomain.isNotEmpty()) {
            hosts.putAll(blkDomain.map { it to AppConfig.LOOPBACK })
        }
        hosts[AppConfig.GOOGLEAPIS_CN_DOMAIN] = AppConfig.GOOGLEAPIS_COM_DOMAIN
        hosts[AppConfig.DNS_ALIDNS_DOMAIN] = AppConfig.DNS_ALIDNS_ADDRESSES
        hosts[AppConfig.DNS_CLOUDFLARE_ONE_DOMAIN] = AppConfig.DNS_CLOUDFLARE_ONE_ADDRESSES
        hosts[AppConfig.DNS_CLOUDFLARE_DNS_COM_DOMAIN] = AppConfig.DNS_CLOUDFLARE_DNS_COM_ADDRESSES
        hosts[AppConfig.DNS_CLOUDFLARE_DNS_DOMAIN] = AppConfig.DNS_CLOUDFLARE_DNS_ADDRESSES
        hosts[AppConfig.DNS_DNSPOD_DOMAIN] = AppConfig.DNS_DNSPOD_ADDRESSES
        hosts[AppConfig.DNS_GOOGLE_DOMAIN] = AppConfig.DNS_GOOGLE_ADDRESSES
        hosts[AppConfig.DNS_QUAD9_DOMAIN] = AppConfig.DNS_QUAD9_ADDRESSES
        hosts[AppConfig.DNS_YANDEX_DOMAIN] = AppConfig.DNS_YANDEX_ADDRESSES
        val userHosts = MmkvManager.decodeSettingsString(AppConfig.PREF_DNS_HOSTS)
        if (userHosts.isNotNullEmpty()) {
            val userHostsMap = userHosts?.split(",")
                ?.filter { it.isNotEmpty() }
                ?.filter { it.contains(":") }
                ?.associate { it.split(":").let { (k, v) -> k to v } }
            if (userHostsMap != null) {
                hosts.putAll(userHostsMap)
            }
        }
        v2rayConfig.dns = V2rayConfig.DnsBean(
            servers = servers,
            hosts = hosts,
            tag = AppConfig.TAG_DNS,
            enableParallelQuery = if ((domesticDns.size + remoteDns.size) > 2) true else null
        )
        v2rayConfig.routing.rules.add(
            V2rayConfig.RoutingBean.RulesBean(
                outboundTag = AppConfig.TAG_DIRECT,
                inboundTag = domesticDnsTags,
                domain = null
            )
        )
        val dnsProxyBalancerTag = policyGroupBalancerTags[AppConfig.TAG_PROXY]
        if (dnsProxyBalancerTag != null) {
            v2rayConfig.routing.rules.add(
                V2rayConfig.RoutingBean.RulesBean(
                    balancerTag = dnsProxyBalancerTag,
                    inboundTag = arrayListOf(AppConfig.TAG_DNS),
                    domain = null
                )
            )
        } else {
            v2rayConfig.routing.rules.add(
                V2rayConfig.RoutingBean.RulesBean(
                    outboundTag = AppConfig.TAG_PROXY,
                    inboundTag = arrayListOf(AppConfig.TAG_DNS),
                    domain = null
                )
            )
        }
    }

    //endregion

    //region outbound related functions

    private fun resolveOutboundDomainsToHosts(v2rayConfig: V2rayConfig) {
        if (MmkvManager.decodeSettingsString(AppConfig.PREF_OUTBOUND_DOMAIN_RESOLVE_METHOD, "1") != "1") return
        val proxyOutboundList = v2rayConfig.getAllProxyOutbound()
        val dns = v2rayConfig.dns ?: return
        val newHosts = dns.hosts?.toMutableMap() ?: mutableMapOf()
        val preferIpv6 = MmkvManager.decodeSettingsBool(AppConfig.PREF_PREFER_IPV6) == true
        for (item in proxyOutboundList) {
            val domain = item.getServerAddress()
            if (domain.isNullOrEmpty()) continue
            if (newHosts.containsKey(domain)) {
                item.ensureSockopt().domainStrategy = "UseIP"
                item.ensureSockopt().happyEyeballs = V2rayConfig.OutboundBean.StreamSettingsBean.HappyEyeballsBean(
                    prioritizeIPv6 = preferIpv6, interleave = 2
                )
                continue
            }
            val resolvedIps = HttpUtil.resolveHostToIP(domain, preferIpv6)
            if (resolvedIps.isNullOrEmpty()) continue
            item.ensureSockopt().domainStrategy = "UseIP"
            item.ensureSockopt().happyEyeballs = V2rayConfig.OutboundBean.StreamSettingsBean.HappyEyeballsBean(
                prioritizeIPv6 = preferIpv6, interleave = 2
            )
            newHosts[domain] = if (resolvedIps.size == 1) resolvedIps[0] else resolvedIps
        }
        dns.hosts = newHosts
    }

    private fun convertProfile2Outbound(profileItem: ProfileItem): V2rayConfig.OutboundBean? {
        return CoreOutboundBuilder.convert(profileItem)
    }

    //endregion

    //region routing related functions

    private fun applyObservability(v2rayConfig: V2rayConfig, strategies: List<BalancerStrategy>) {
        val allObsSelectors = strategies.mapNotNull { it.observatory?.subjectSelector }.flatten().distinct()
        val obsTemplate = strategies.firstNotNullOfOrNull { it.observatory }
        if (obsTemplate != null && allObsSelectors.isNotEmpty()) {
            v2rayConfig.observatory = V2rayConfig.ObservatoryObject(
                subjectSelector = allObsSelectors,
                probeUrl = obsTemplate.probeUrl,
                probeInterval = obsTemplate.probeInterval,
                enableConcurrency = obsTemplate.enableConcurrency
            )
        }
        val allBurstSelectors = strategies.mapNotNull { it.burstObservatory?.subjectSelector }.flatten().distinct()
        val burstTemplate = strategies.firstNotNullOfOrNull { it.burstObservatory }
        if (burstTemplate != null && allBurstSelectors.isNotEmpty()) {
            v2rayConfig.burstObservatory = V2rayConfig.BurstObservatoryObject(
                subjectSelector = allBurstSelectors,
                pingConfig = burstTemplate.pingConfig
            )
        }
    }

    private fun configureRouting(
        configContext: CoreConfigContext,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: Map<String, String>
    ) {
        v2rayConfig.routing.domainStrategy = MmkvManager.decodeSettingsString(AppConfig.PREF_ROUTING_DOMAIN_STRATEGY) ?: "AsIs"
        val rulesetItems = MmkvManager.decodeRoutingRulesets()
        rulesetItems?.forEach { key ->
            appendRoutingUserRule(configContext, key, v2rayConfig, policyGroupBalancerTags)
        }
    }

    private fun appendRoutingUserRule(
        configContext: CoreConfigContext,
        item: RulesetItem?,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: Map<String, String>
    ) {
        val context = configContext.context
        if (item == null || !item.enabled) return
        val rule = JsonUtil.fromJson(JsonUtil.toJson(item), V2rayConfig.RoutingBean.RulesBean::class.java) ?: return
        rule.ip?.let { ipList ->
            val updatedIpList = ArrayList<String>()
            ipList.forEach { ip ->
                when (ip) {
                    AppConfig.GEOIP_CN -> updatedIpList.add("ext:${AppConfig.GEOIP_ONLY_CN_PRIVATE_DAT}:cn")
                    AppConfig.GEOIP_PRIVATE -> updatedIpList.add("ext:${AppConfig.GEOIP_ONLY_CN_PRIVATE_DAT}:private")
                    else -> updatedIpList.add(ip)
                }
            }
            rule.ip = updatedIpList
        }
        if (SettingsManager.canUseProcessRouting()) {
            rule.process?.let { processList ->
                if (processList.isNotEmpty()) {
                    val uids = PackageUidResolver.packageNamesToUids(context, processList)
                    rule.process = uids.ifEmpty { null }
                }
            }
        } else {
            rule.process = null
        }
        val outboundTag = rule.outboundTag
        policyGroupBalancerTags[outboundTag]?.let { balancerTag ->
            rule.outboundTag = null
            rule.balancerTag = balancerTag
        }
        if (!outboundTag.isNullOrBlank()
            && outboundTag !in policyGroupBalancerTags
            && outboundTag !in AppConfig.BUILTIN_OUTBOUND_TAGS
            && v2rayConfig.outbounds.none { it.tag == outboundTag }
        ) {
            LogUtil.w(AppConfig.TAG, "Outbound tag '$outboundTag' not found, falling back to '${AppConfig.TAG_PROXY}'")
            rule.outboundTag = AppConfig.TAG_PROXY
        }
        v2rayConfig.routing.rules.add(rule)
    }

    private fun buildBalancerStrategy(
        policyGroupType: String?,
        selector: List<String>,
        balancerTag: String = AppConfig.TAG_BALANCER,
    ): BalancerStrategy {
        val probeUrl = MmkvManager.decodeSettingsString(AppConfig.PREF_DELAY_TEST_URL) ?: AppConfig.DELAY_TEST_URL
        val strategyType = BalancerStrategyType.from(policyGroupType)
        val balancer = V2rayConfig.RoutingBean.BalancerBean(
            tag = balancerTag,
            selector = selector,
            strategy = V2rayConfig.RoutingBean.StrategyObject(type = strategyType.policyGroupType)
        )
        val observatory = if (strategyType.requiresObservatory) {
            V2rayConfig.ObservatoryObject(
                subjectSelector = selector,
                probeUrl = probeUrl,
                probeInterval = "3m",
                enableConcurrency = true
            )
        } else null
        val burstObservatory = if (strategyType.requiresBurstObservatory) {
            V2rayConfig.BurstObservatoryObject(
                subjectSelector = selector,
                pingConfig = V2rayConfig.BurstObservatoryObject.PingConfigObject(
                    destination = probeUrl,
                    interval = "5m",
                    sampling = 2,
                    timeout = "30s"
                )
            )
        } else null
        return BalancerStrategy(balancer, observatory, burstObservatory)
    }

    private data class BalancerStrategy(
        val balancer: V2rayConfig.RoutingBean.BalancerBean,
        val observatory: V2rayConfig.ObservatoryObject? = null,
        val burstObservatory: V2rayConfig.BurstObservatoryObject? = null,
    )

    // ------------------------------------------------------------------
    // Custom outbound injection with chain proxy support
    // ------------------------------------------------------------------

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

    private fun applySubscriptionChain(
        v2rayConfig: V2rayConfig,
        profile: ProfileItem,
        outbound: V2rayConfig.OutboundBean,
        outboundTagMap: MutableMap<String, String>,
        existingTags: MutableSet<String>
    ) {
        var subItem: SubscriptionItem? = null
        
        // Try to get subscription from the profile
        if (!profile.subscriptionId.isNullOrEmpty()) {
            subItem = MmkvManager.decodeSubscription(profile.subscriptionId)
        }
        
        // If profile has no subscription, check if the outbound tag is the current server
        // and get subscription from there? For now, log and return
        if (subItem == null) {
            LogUtil.d(AppConfig.TAG, "⚠️ No subscription for profile '${profile.remarks}', cannot apply chain")
            return
        }
        
        val originalTag = outbound.tag
        LogUtil.d(AppConfig.TAG, "🔗 Applying chain for '$originalTag' using subscription ${subItem.remarks}")
        LogUtil.d(AppConfig.TAG, "   prevProfile='${subItem.prevProfile}', nextProfile='${subItem.nextProfile}'")

        fun addChainOutbound(
            targetRemark: String?,
            chainType: String,
            desiredTag: String,
            chainTo: (V2rayConfig.OutboundBean) -> Unit
        ) {
            val resolvedRemark = resolveCurrentServer(targetRemark)
            if (resolvedRemark.isNullOrEmpty()) {
                LogUtil.d(AppConfig.TAG, "⚠️ $chainType target is empty or None, skipping")
                return
            }

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
            
            val mainRemarks = MmkvManager.getSelectServer()?.let { MmkvManager.decodeServerConfig(it)?.remarks }
            if (chainProfile.remarks == mainRemarks) {
                outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                LogUtil.d(AppConfig.TAG, "✅ $chainType proxy is main server, set dialerProxy to proxy")
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
            LogUtil.d(AppConfig.TAG, "✅ Created $chainType outbound: $desiredTag")
        }

        addChainOutbound(subItem.prevProfile, "prev", "$originalTag-prev") { prevOutbound ->
            outbound.ensureSockopt().dialerProxy = prevOutbound.tag
            LogUtil.d(AppConfig.TAG, "🔗 Wired prev: ${outbound.tag}.dialerProxy = ${prevOutbound.tag}")
        }

        if (!subItem.nextProfile.isNullOrEmpty()) {
            val newOriginalTag = "$originalTag-orig"
            val oldTag = outbound.tag
            outbound.tag = newOriginalTag
            LogUtil.d(AppConfig.TAG, "📝 Renamed outbound from '$oldTag' to '$newOriginalTag' for next chain")

            addChainOutbound(subItem.nextProfile, "next", originalTag) { nextOutbound ->
                nextOutbound.ensureSockopt().dialerProxy = newOriginalTag
                LogUtil.d(AppConfig.TAG, "🔗 Wired next: ${nextOutbound.tag}.dialerProxy = $newOriginalTag")
            }
        } else {
            LogUtil.d(AppConfig.TAG, "ℹ️ No nextProfile configured, skipping next hop")
        }
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

    //endregion
}
'''

def patch_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found – skipping")
        return
    backup_kotlin(p)
    write(p, PATCHED_CORECONFIG_MANAGER)
    print("✓ CoreConfigManager.kt replaced with fully patched + logging version")

def main():
    print("=" * 70)
    print("Final Patcher – fixes [Current Server] chain handling with detailed logging")
    print("=" * 70)

    try:
        patch_appconfig()
        patch_subedit()
        patch_strings()
        patch_coreconfigcontextbuilder()
        patch_coreconfigmanager()
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild and run: adb logcat | grep -E 'com.v2ray.ang|🔗|🎯|❌'")
        print("   This will show which profile fails to convert in the chain.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

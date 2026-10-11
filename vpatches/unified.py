#!/usr/bin/env python3
"""
v2rayNG patcher for 2dust/v2rayNG master — unified.

Enables CUSTOM profiles everywhere they are currently rejected, carries
their raw JSON losslessly through the whole pipeline, and deduplicates
identical chain-hop outbounds.

Replaces the two previously separate patchers. Idempotent: safe to run
on clean master, or after either prior patcher.
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path("V2rayNG")


def backup_kotlin(p: Path):
    if p.suffix != ".kt":
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_suffix(f".kt.bak.{ts}")
    shutil.copy2(p, bak)
    print(f"  backup: {bak.name}")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


def _has_real_field(c: str, field: str) -> bool:
    """Match a real declaration, not a docstring reference."""
    return re.search(
        rf'(?m)^\s*(@Transient\s+)?(var|val)\s+{re.escape(field)}\b', c
    ) is not None


# ======================================================================
# A. Data model
# ======================================================================
def patch_profileitem():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/entities/ProfileItem.kt"
    if not p.exists():
        print("✗ ProfileItem.kt not found")
        return
    c = read(p)

    if _has_real_field(c, "customConfigRaw"):
        print("• ProfileItem: customConfigRaw already declared")
        return

    old = '''    companion object {
        fun create(configType: EConfigType): ProfileItem =
            ProfileItem(configType = configType)
    }'''
    new = '''    /**
     * Raw JSON of a CUSTOM profile, populated in-memory by
     * MmkvManager.decodeServerConfig. Never persisted; used only to
     * extract the proxy outbound when a CUSTOM profile is used as a
     * sub-outbound (chain, policy-group member, routing target).
     *
     * @Transient marks the backing field transient so Gson skips it on
     * encode — no need to strip it in encodeServerConfig.
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


def patch_v2rayconfig_rawjson():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/V2rayConfig.kt"
    if not p.exists():
        print("✗ V2rayConfig.kt not found")
        return
    c = read(p)

    if "var rawJson" in c:
        print("• V2rayConfig: rawJson already present")
        return

    if "import com.google.gson.JsonObject" not in c:
        anchor = "import com.google.gson.annotations.SerializedName"
        if anchor in c:
            c = c.replace(
                anchor,
                "import com.google.gson.JsonObject\n" + anchor,
                1,
            )

    old = '''    data class OutboundBean(
        var tag: String = "proxy",
        var protocol: String,
        var settings: OutSettingsBean? = null,
        var streamSettings: StreamSettingsBean? = null,
        val sendThrough: String? = null,
        var mux: MuxBean? = MuxBean(false),
        var targetStrategy: String? = null
    ) {'''
    new = '''    data class OutboundBean(
        var tag: String = "proxy",
        var protocol: String,
        var settings: OutSettingsBean? = null,
        var streamSettings: StreamSettingsBean? = null,
        val sendThrough: String? = null,
        var mux: MuxBean? = MuxBean(false),
        var targetStrategy: String? = null
    ) {
        /**
         * Raw JSON of a CUSTOM outbound. When set, CoreConfigManager
         * substitutes this object into the serialized config instead of
         * the typed fields above, preserving protocol-specific settings
         * (masque, tuic, ...) that the app's data model does not know
         * about. @Transient keeps Gson from ever emitting it.
         */
        @Transient
        var rawJson: JsonObject? = null
'''
    if old in c:
        c = c.replace(old, new, 1)
        backup_kotlin(p)
        write(p, c)
        print("✓ V2rayConfig: added @Transient rawJson to OutboundBean")
    else:
        print("⚠ V2rayConfig: OutboundBean declaration not matched")


def patch_mmkvmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/handler/MmkvManager.kt"
    if not p.exists():
        print("✗ MmkvManager.kt not found")
        return
    c = read(p)

    if re.search(r'item\.customConfigRaw\s*=', c):
        print("• MmkvManager: customConfigRaw already populated")
        return

    if "import com.v2ray.ang.enums.EConfigType" not in c:
        anchor = "import com.v2ray.ang.dto.entities.ProfileItem"
        if anchor in c:
            c = c.replace(
                anchor,
                anchor + "\nimport com.v2ray.ang.enums.EConfigType",
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


# ======================================================================
# B. Config context builder — allow CUSTOM in every sub-outbound slot
# ======================================================================
def patch_coreconfigcontextbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"
    if not p.exists():
        print("✗ CoreConfigContextBuilder.kt not found")
        return
    c = read(p)
    changed = False

    # 1. Remove the early CUSTOM short-circuit in resolveOutbound.
    guard_pat = re.compile(
        r'^[ \t]*if \(profile\.configType == EConfigType\.CUSTOM\) \{\s*'
        r'\n[ \t]*return null\s*\n[ \t]*\}\n',
        re.MULTILINE,
    )
    c2, n = guard_pat.subn("", c, count=1)
    if n > 0:
        c = c2
        changed = True
        print("✓ CoreConfigContextBuilder: removed CUSTOM guard in resolveOutbound")

    # 2. Replace `!isComplexType()` / `!isGroupType()` type filters so that
    #    CUSTOM survives. Complements the endpoint filter fix below.
    filt_pat = re.compile(
        r'^(?P<indent>[ \t]*)\.filter\s*\{\s*!\s*it\.configType\.'
        r'(?:isComplexType|isGroupType)\(\)\s*\}',
        re.MULTILINE,
    )

    def filt_repl(m):
        indent = m.group("indent")
        return (
            f'{indent}.filter {{ it.configType != EConfigType.POLICYGROUP '
            f'&& it.configType != EConfigType.PROXYCHAIN }}'
        )

    c, n = filt_pat.subn(filt_repl, c)
    if n > 0:
        changed = True
        print(f"✓ CoreConfigContextBuilder: replaced {n} complex-type filter(s)")

    # 3. Relax the endpoint sanity filter. A CUSTOM profile parsed from a
    #    real Xray config typically has `server == null` (the address lives
    #    in settings.vnext[0].address, not settings.address), so requiring
    #    a valid server drops every CUSTOM profile before it can be used.
    old_pair = re.compile(
        r'^(?P<indent>[ \t]*)\.filter \{ it\.server\.isNotNullEmpty\(\) \}\s*\n'
        r'[ \t]*\.filter \{ Utils\.isPureIpAddress\(it\.server!!\) \|\| '
        r'Utils\.isValidUrl\(it\.server!!\) \}',
        re.MULTILINE,
    )

    def pair_repl(m):
        indent = m.group("indent")
        return (
            f'{indent}.filter {{\n'
            f'{indent}    it.configType == EConfigType.CUSTOM ||\n'
            f'{indent}        (it.server.isNotNullEmpty() &&\n'
            f'{indent}            (Utils.isPureIpAddress(it.server!!) '
            f'|| Utils.isValidUrl(it.server!!)))\n'
            f'{indent}}}'
        )

    c, n = old_pair.subn(pair_repl, c)
    if n > 0:
        changed = True
        print(f"✓ CoreConfigContextBuilder: relaxed server filter for CUSTOM ({n} site(s))")

    # 4. Fallback outbound may now be a CUSTOM profile too.
    old_fb = (
        '?.takeUnless { it.configType == EConfigType.CUSTOM '
        '|| it.configType == EConfigType.POLICYGROUP }'
    )
    if old_fb in c:
        c = c.replace(
            old_fb,
            '?.takeUnless { it.configType == EConfigType.POLICYGROUP }',
            1,
        )
        changed = True
        print("✓ CoreConfigContextBuilder: fallback outbound accepts CUSTOM")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ======================================================================
# C. Outbound builder — dispatch CUSTOM and produce a lossless outbound
# ======================================================================
_LOSSLESS_TO_OUTBOUND_CUSTOM = '''
    /**
     * Extracts the proxy outbound from a CUSTOM profile's raw JSON as a
     * raw JsonObject so protocol-specific fields the app does not model
     * (masque, tuic, ...) survive intact. The caller assigns a tag and
     * CoreConfigManager substitutes this object back into the serialized
     * config.
     */
    private fun toOutboundCustom(profileItem: ProfileItem): OutboundBean? {
        val raw = profileItem.customConfigRaw ?: return null
        return try {
            val root = JsonUtil.parseString(raw) ?: return null
            val outbounds = root.getAsJsonArray("outbounds") ?: return null

            val objs = outbounds
                .filter { it.isJsonObject }
                .map { it.asJsonObject }
            val proxyObj = objs.firstOrNull { it.get("tag")?.asString == AppConfig.TAG_PROXY }
                ?: objs.firstOrNull { ob ->
                    val proto = ob.get("protocol")?.asString?.lowercase()
                    proto != null && proto !in setOf("freedom", "blackhole", "dns")
                }
                ?: return null

            val protocol = proxyObj.get("protocol")?.asString ?: return null
            val bean = OutboundBean(protocol = protocol)
            bean.tag = ""
            bean.rawJson = proxyObj.deepCopy()
            bean
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to extract outbound from CUSTOM profile", e)
            null
        }
    }
'''


def patch_coreoutboundbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreOutboundBuilder.kt"
    if not p.exists():
        print("✗ CoreOutboundBuilder.kt not found")
        return
    c = read(p)
    changed = False

    # 1. Make sure the outer V2rayConfig type is importable (used for the
    #    top-level custom-config model).
    if "import com.v2ray.ang.dto.V2rayConfig\n" not in c:
        anchor = "import com.v2ray.ang.dto.V2rayConfig.OutboundBean"
        if anchor in c:
            c = c.replace(anchor, "import com.v2ray.ang.dto.V2rayConfig\n" + anchor, 1)
            changed = True
            print("✓ CoreOutboundBuilder: added `import com.v2ray.ang.dto.V2rayConfig`")

    # 2. Add dispatch case.
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

    # 3. Skip global mux override for CUSTOM (it carries its own transport).
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
    if old_ret in c:
        c = c.replace(old_ret, new_ret, 1)
        changed = True
        print("✓ CoreOutboundBuilder: skip global mux override for CUSTOM")

    # 4. toOutboundCustom — insert if absent, rewrite if the lossy variant
    #    from the older patcher is present.
    func_pat = re.compile(
        r'\n    private fun toOutboundCustom\(profileItem: ProfileItem\): OutboundBean\? '
        r'\{(?:.|\n)*?\n    \}\n',
    )
    m = func_pat.search(c)
    if m is None:
        last_brace = c.rfind('}')
        if last_brace == -1:
            print("⚠ CoreOutboundBuilder: closing brace not found")
        else:
            c = c[:last_brace] + _LOSSLESS_TO_OUTBOUND_CUSTOM + c[last_brace:]
            changed = True
            print("✓ CoreOutboundBuilder: inserted lossless toOutboundCustom")
    elif "bean.rawJson = proxyObj.deepCopy()" in m.group(0):
        print("• CoreOutboundBuilder: toOutboundCustom already lossless")
    else:
        c = c[:m.start()] + _LOSSLESS_TO_OUTBOUND_CUSTOM + c[m.end():]
        changed = True
        print("✓ CoreOutboundBuilder: replaced lossy toOutboundCustom")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ======================================================================
# D. Config manager — chain-hop dedup + raw-JSON substitution
# ======================================================================
_NEW_CHAIN_HANDLER = '''    private fun handleProxyChainResolvedOutbound(
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
        // chains that share a suffix produce the same signature at the
        // first shared index, letting a single outbound serve both.
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

        val chainTags = MutableList(n) { "" }
        chainTags[0] = resolvedOutbound.tag
        val newHops = mutableListOf<V2rayConfig.OutboundBean>()
        newHops.add(chainOutbounds[0])

        for (i in 1 until n) {
            val hop = chainOutbounds[i]
            val sig = suffixSig[i]!!
            val existingTag = chainHopDedup[sig]
            if (existingTag != null) {
                chainTags[i] = existingTag
            } else {
                val newTag = "${AppConfig.TAG_PROXY}-${resolvedOutbound.tag}-$i"
                if (newTag in existingTags) {
                    LogUtil.w(
                        AppConfig.TAG,
                        "PROXYCHAIN resolved outbound '${resolvedOutbound.tag}' has colliding hop tags, skipping"
                    )
                    // Roll back this chain's just-added tags so a later
                    // successful chain can reuse the suffixes.
                    newHops.forEach { existingTags.remove(it.tag) }
                    val removedTags = newHops.map { it.tag }.toSet()
                    chainHopDedup.entries.removeAll { it.value in removedTags }
                    return
                }
                hop.tag = newTag
                chainTags[i] = newTag
                newHops.add(hop)
                existingTags.add(newTag)
                chainHopDedup[sig] = newTag
            }
        }

        // Wire dialerProxy on each newly-added hop to its successor. The
        // successor may be a hop reused from a previous chain, so we look
        // it up by index in the original chainOutbounds list.
        newHops.forEach { outbound ->
            val chainIndex = chainOutbounds.indexOf(outbound)
            if (chainIndex in 0 until n - 1) {
                outbound.ensureSockopt().dialerProxy = chainTags[chainIndex + 1]
            }
        }

        if (prepend) {
            v2rayConfig.outbounds.addAll(0, newHops)
        } else {
            v2rayConfig.outbounds.addAll(newHops)
        }
    }

    /**
     * Canonical content signature of an outbound. Ignores tag and any
     * chain-specific dialerProxy so identical hops compare equal. For
     * CUSTOM sub-outbounds whose real payload is rawJson, signs the raw
     * JSON instead of the (empty) typed fields.
     */
    private fun outboundContentSignature(outbound: V2rayConfig.OutboundBean): String {
        outbound.rawJson?.let { raw ->
            val copy = raw.deepCopy()
            copy.remove("tag")
            copy.getAsJsonObject("streamSettings")
                ?.getAsJsonObject("sockopt")
                ?.remove("dialerProxy")
            return copy.toString()
        }
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
    }
'''


def patch_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)
    changed = False

    # ---- 1. chainHopDedup map creation --------------------------------
    if "val chainHopDedup" not in c:
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

    # ---- 2. Extend buildOutbounds signature ---------------------------
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

    # ---- 3. Forward chainHopDedup into the chain branch ---------------
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

    # ---- 4. Replace handleProxyChainResolvedOutbound -------------------
    handler_pat = re.compile(
        r'    private fun handleProxyChainResolvedOutbound\(\s*'
        r'resolvedOutbound: CoreConfigContext\.ResolvedOutbound,\s*'
        r'prepend: Boolean,\s*'
        r'existingTags: MutableSet<String>,\s*'
        r'v2rayConfig: V2rayConfig,'
        r'(?:\s*chainHopDedup: MutableMap<String, String>,)?\s*'
        r'\) \{(?:.|\n)*?\n    \}',
    )
    m = handler_pat.search(c)
    if m is None:
        print("⚠ CoreConfigManager: handleProxyChainResolvedOutbound not found")
    elif "chainHopDedup: MutableMap<String, String>" in m.group(0):
        print("• CoreConfigManager: handleProxyChainResolvedOutbound already unified")
    else:
        c = c[:m.start()] + _NEW_CHAIN_HANDLER.rstrip() + c[m.end():]
        changed = True
        print("✓ CoreConfigManager: rewrote handleProxyChainResolvedOutbound with dedup")

    # ---- 5. toConfigResult: substitute raw JSON back into output ------
    if "substituteRawOutbounds" not in c:
        old_tcr = '''    private fun toConfigResult(configContext: CoreConfigContext, v2rayConfig: V2rayConfig): ConfigResult {
        return ConfigResult(
            status = true,
            guid = configContext.guid,
            content = JsonUtil.toJsonPretty(v2rayConfig) ?: ""
        )
    }'''
        new_tcr = '''    private fun toConfigResult(configContext: CoreConfigContext, v2rayConfig: V2rayConfig): ConfigResult {
        val serialized = JsonUtil.toJsonPretty(v2rayConfig) ?: ""
        val content = substituteRawOutbounds(serialized, v2rayConfig)
        return ConfigResult(
            status = true,
            guid = configContext.guid,
            content = content
        )
    }

    /**
     * Replaces any outbound carrying a raw JSON payload with that payload,
     * so CUSTOM sub-outbounds (masque, tuic, ...) round-trip losslessly
     * through the config pipeline. The typed tag and any chain-mutation
     * (dialerProxy) are overlaid on top of the raw JSON.
     */
    private fun substituteRawOutbounds(json: String, v2rayConfig: V2rayConfig): String {
        val rawByTag = v2rayConfig.outbounds
            .filter { it.rawJson != null }
            .associateBy({ it.tag }, { it })
        if (rawByTag.isEmpty()) return json

        val root = JsonUtil.parseString(json) ?: return json
        val outbounds = root.getAsJsonArray("outbounds") ?: return json
        for (i in 0 until outbounds.size()) {
            val ob = outbounds.get(i).takeIf { it.isJsonObject }?.asJsonObject ?: continue
            val tag = ob.get("tag")?.asString ?: continue
            val bean = rawByTag[tag] ?: continue

            // Deep-copy so the profile's cached raw JSON is never mutated.
            val replacement = bean.rawJson!!.deepCopy()
            replacement.addProperty("tag", tag)

            // Preserve the chain dialerProxy the pipeline wired onto the
            // typed bean.
            val dialerProxy = bean.streamSettings?.sockopt?.dialerProxy
            if (!dialerProxy.isNullOrEmpty()) {
                val streamSettings = replacement.getAsJsonObject("streamSettings")
                    ?: JsonObject().also { replacement.add("streamSettings", it) }
                val sockopt = streamSettings.getAsJsonObject("sockopt")
                    ?: JsonObject().also { streamSettings.add("sockopt", it) }
                sockopt.addProperty("dialerProxy", dialerProxy)
            }

            outbounds.set(i, replacement)
        }
        return JsonUtil.toJsonPretty(root) ?: json
    }'''
        if old_tcr in c:
            c = c.replace(old_tcr, new_tcr, 1)
            changed = True
            print("✓ CoreConfigManager: added substituteRawOutbounds")
        else:
            print("⚠ CoreConfigManager: toConfigResult body not matched")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ======================================================================
# E. UI pickers — allow CUSTOM in chain / routing / subscription pickers
# ======================================================================
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

    old_valid_re = re.compile(
        r'profile\s*==\s*null\s*\|\|\s*profile\.configType\.(?:isComplexType|isGroupType)\(\)'
    )
    new_valid = (
        '(profile == null) ||\n'
        '                    (profile.configType == EConfigType.POLICYGROUP) ||\n'
        '                    (profile.configType == EConfigType.PROXYCHAIN)'
    )
    c2, n = old_valid_re.subn(new_valid, c)
    if n > 0:
        c = c2
        changed = True
        print("✓ ServerProxyChainActivity: validation accepts CUSTOM")

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
    new = (
        '        val profileRemarks = SettingsManager.getProfileRemarks(\n'
        '            excludeConfigTypes = setOf(EConfigType.POLICYGROUP, EConfigType.PROXYCHAIN)\n'
        '        )'
    )
    if old in c:
        c = c.replace(old, new, 1)
        if "import com.v2ray.ang.enums.EConfigType" not in c:
            anchor = "import com.v2ray.ang.dto.entities.RulesetItem"
            if anchor in c:
                c = c.replace(
                    anchor,
                    anchor + "\nimport com.v2ray.ang.enums.EConfigType",
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


# ======================================================================
def main():
    print("=" * 70)
    print("Unified patcher: CUSTOM everywhere + lossless JSON + chain dedup")
    print("=" * 70)
    try:
        # A. Data model
        patch_profileitem()
        patch_v2rayconfig_rawjson()
        patch_mmkvmanager()

        # B. Config context
        patch_coreconfigcontextbuilder()

        # C. Outbound builder (lossless)
        patch_coreoutboundbuilder()

        # D. Config manager (dedup + substitute)
        patch_coreconfigmanager()

        # E. UI pickers
        patch_serverproxychain_activity()
        patch_routingedit_activity()
        patch_subedit_activity()

        print("\n✅ Done. Rebuild and test.")
        print("   cd V2rayNG && ./gradlew :app:testPlaystoreDebugUnitTest "
              ":app:compilePlaystoreDebugKotlin")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

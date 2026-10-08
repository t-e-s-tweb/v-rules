#!/usr/bin/env python3
"""
Fix: preserve the full JSON of a CUSTOM sub-outbound (masque, tuic, ...)
through serialization.

Root cause: toOutboundCustom round-tripped the outbound through
V2rayConfig / OutboundBean data classes, so any field Gson did not model
(settings for a protocol the app doesn't know) was dropped. Replaced with
a raw JsonObject passthrough.

Adds:
  • @Transient rawJson on OutboundBean
  • toOutboundCustom now parses raw JSON and stores it as-is
  • CoreConfigManager.toConfigResult substitutes the raw JSON back into
    the serialized output, overlaying the tag and any chain dialerProxy.

Idempotent.
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path("V2rayNG")


def backup_kotlin(p: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(p, p.with_suffix(f".kt.bak.{ts}"))
    print(f"  backup: {p.with_suffix(f'.kt.bak.{ts}').name}")


def read(p):
    return p.read_text(encoding="utf-8")


def write(p, s):
    p.write_text(s, encoding="utf-8")


# ----------------------------------------------------------------------
# 1. V2rayConfig.kt – add @Transient rawJson to OutboundBean
# ----------------------------------------------------------------------
def patch_v2rayconfig_rawjson():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/V2rayConfig.kt"
    if not p.exists():
        print("✗ V2rayConfig.kt not found")
        return
    c = read(p)

    if "var rawJson" in c:
        print("• V2rayConfig: rawJson already present")
        return

    # Ensure JsonObject is importable
    if "import com.google.gson.JsonObject" not in c:
        c = c.replace(
            "import com.google.gson.annotations.SerializedName",
            "import com.google.gson.JsonObject\nimport com.google.gson.annotations.SerializedName",
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
         * about. Marked @Transient so Gson never emits it.
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


# ----------------------------------------------------------------------
# 2. CoreOutboundBuilder.kt – keep the raw JSON, don't round-trip
# ----------------------------------------------------------------------
def patch_coreoutboundbuilder_rawjson():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreOutboundBuilder.kt"
    if not p.exists():
        print("✗ CoreOutboundBuilder.kt not found")
        return
    c = read(p)

    old = '''    private fun toOutboundCustom(profileItem: ProfileItem): OutboundBean? {
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
    }'''
    new = '''    private fun toOutboundCustom(profileItem: ProfileItem): OutboundBean? {
        val raw = profileItem.customConfigRaw ?: return null
        return try {
            // Parse as a raw JsonObject, NOT as V2rayConfig, so that
            // protocol-specific fields (masque settings, tuic fields, ...)
            // are preserved verbatim. CoreConfigManager substitutes this
            // object into the serialized config.
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
    }'''
    if old in c:
        c = c.replace(old, new, 1)
        backup_kotlin(p)
        write(p, c)
        print("✓ CoreOutboundBuilder: rewrote toOutboundCustom for lossless JSON")
    elif "bean.rawJson = proxyObj.deepCopy()" in c:
        print("• CoreOutboundBuilder: toOutboundCustom already lossless")
    else:
        print("⚠ CoreOutboundBuilder: toOutboundCustom body not matched")


# ----------------------------------------------------------------------
# 3. CoreConfigManager.kt – substitute raw JSON back into the output
# ----------------------------------------------------------------------
def patch_coreconfigmanager_substitute():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)

    if "substituteRawOutbounds" in c:
        print("• CoreConfigManager: substituteRawOutbounds already present")
        return

    old = '''    private fun toConfigResult(configContext: CoreConfigContext, v2rayConfig: V2rayConfig): ConfigResult {
        return ConfigResult(
            status = true,
            guid = configContext.guid,
            content = JsonUtil.toJsonPretty(v2rayConfig) ?: ""
        )
    }'''
    new = '''    private fun toConfigResult(configContext: CoreConfigContext, v2rayConfig: V2rayConfig): ConfigResult {
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

            // Deep-copy so we never mutate the profile's cached raw JSON.
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
    if old in c:
        c = c.replace(old, new, 1)
        backup_kotlin(p)
        write(p, c)
        print("✓ CoreConfigManager: added substituteRawOutbounds")
    else:
        print("⚠ CoreConfigManager: toConfigResult body not matched")


def main():
    print("=" * 70)
    print("Fix: lossless CUSTOM sub-outbound JSON passthrough")
    print("=" * 70)
    try:
        patch_v2rayconfig_rawjson()
        patch_coreoutboundbuilder_rawjson()
        patch_coreconfigmanager_substitute()
        print("\n✅ Done.")
        print("👉 Rebuild and test.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

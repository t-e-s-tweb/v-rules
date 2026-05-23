#!/usr/bin/env python3
"""
Unified patcher for v2rayNG (final reliable version).
- Adds custom outbound injection with prev/next chaining.
- Enhances SubEditActivity dropdown with None and [Current Server].
- Adds AppConfig.CURRENT_SERVER constant.
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

# ─────────────────────────────────────────────────────────────────────────
# 1. AppConfig.kt – add CURRENT_SERVER constant if missing
# ─────────────────────────────────────────────────────────────────────────
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    c = read(p)
    if '"__CURRENT_SERVER__"' in c:
        print("• AppConfig: CURRENT_SERVER already present")
        return
    old = '    const val TAG_BLOCKED = "block"'
    new = '    const val TAG_BLOCKED = "block"\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"'
    if old in c:
        write(p, c.replace(old, new))
        print("✓ AppConfig: added CURRENT_SERVER")
    else:
        print("✗ AppConfig: insertion point not found")

# ─────────────────────────────────────────────────────────────────────────
# 2. SubEditActivity.kt – add None and [Current Server] to dropdown
# ─────────────────────────────────────────────────────────────────────────
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found – skipping")
        return
    c = read(p)

    # 2.1 replace setupProfileRemarkInputs
    old_setup_inputs = '''    private fun setupProfileRemarkInputs() {
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
    new_setup_inputs = '''    private fun setupProfileRemarkInputs() {
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
    if old_setup_inputs in c:
        c = c.replace(old_setup_inputs, new_setup_inputs)
        print("✓ SubEditActivity: updated setupProfileRemarkInputs")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInputs not found (maybe already patched)")

    # 2.2 replace setupProfileRemarkInput to handle mapping on selection
    old_setup_input = '''    private fun setupProfileRemarkInput(
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
    new_setup_input = '''    private fun setupProfileRemarkInput(
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
    if old_setup_input in c:
        c = c.replace(old_setup_input, new_setup_input)
        print("✓ SubEditActivity: updated setupProfileRemarkInput")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInput not found")

    # 2.3 update bindingServer to display friendly strings
    old_binding = '''        binding.etPreProfile.text = Utils.getEditable(subItem.prevProfile)
        binding.etNextProfile.text = Utils.getEditable(subItem.nextProfile)'''
    new_binding = '''        val preDisplay = when (subItem.prevProfile) {
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
    if old_binding in c:
        c = c.replace(old_binding, new_binding)
        print("✓ SubEditActivity: updated bindingServer")
    else:
        print("⚠ SubEditActivity: bindingServer lines not found")

    # 2.4 update saveServer to convert display back to stored values
    old_save = '''        subItem.prevProfile = binding.etPreProfile.text.toString()
        subItem.nextProfile = binding.etNextProfile.text.toString()'''
    new_save = '''        subItem.prevProfile = when (binding.etPreProfile.text.toString()) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> binding.etPreProfile.text.toString()
        }
        subItem.nextProfile = when (binding.etNextProfile.text.toString()) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> binding.etNextProfile.text.toString()
        }'''
    if old_save in c:
        c = c.replace(old_save, new_save)
        print("✓ SubEditActivity: updated saveServer")
    else:
        print("⚠ SubEditActivity: saveServer lines not found")

    write(p, c)
    print("✓ SubEditActivity: all enhancements applied")

# ─────────────────────────────────────────────────────────────────────────
# 3. strings.xml – add None and [Current Server] resources if missing
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
# 4. CoreConfigManager.kt – inject custom outbounds and chain support (reliable)
# ─────────────────────────────────────────────────────────────────────────
def patch_coreconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found – skipping")
        return
    c = read(p)

    # ------------------------------------------------------------------
    # 1. Insert helper functions right before the final '}' of the object
    # ------------------------------------------------------------------
    if "private fun injectCustomOutbounds" not in c:
        last_brace = c.rfind('}')
        if last_brace == -1:
            print("✗ CoreConfigManager: no closing brace found")
            return
        indent = '    '
        helpers = f'''
{indent}// ------------------------------------------------------------------
{indent}// Custom outbound injection with chain proxy support
{indent}// ------------------------------------------------------------------

{indent}/**
{indent} * Resolves [Current Server] placeholder to the actual selected server's remark.
{indent} */
{indent}private fun resolveCurrentServer(remark: String?): String? {{
{indent}    if (remark == AppConfig.CURRENT_SERVER) {{
{indent}        val currId = MmkvManager.getSelectServer()
{indent}        if (!currId.isNullOrEmpty()) {{
{indent}            val profile = MmkvManager.decodeServerConfig(currId)
{indent}            return profile?.remarks
{indent}        }}
{indent}    }}
{indent}    return remark
{indent}}}

{indent}/**
{indent} * Applies subscription chain (prev/next proxy) to a custom outbound.
{indent} */
{indent}private fun applySubscriptionChain(
{indent}    v2rayConfig: V2rayConfig,
{indent}    profile: ProfileItem,
{indent}    outbound: V2rayConfig.OutboundBean,
{indent}    outboundTagMap: MutableMap<String, String>,
{indent}    existingTags: MutableSet<String>
{indent}) {{
{indent}    if (profile.subscriptionId.isNullOrEmpty()) return

{indent}    val subItem = MmkvManager.decodeSubscription(profile.subscriptionId) ?: return
{indent}    val originalTag = outbound.tag

{indent}    fun addChainOutbound(
{indent}        targetRemark: String?,
{indent}        chainType: String,
{indent}        desiredTag: String,
{indent}        chainTo: (V2rayConfig.OutboundBean) -> Unit
{indent}    ) {{
{indent}        if (targetRemark.isNullOrEmpty()) return

{indent}        val existingByTag = v2rayConfig.outbounds.firstOrNull {{ it.tag == desiredTag }}
{indent}        if (existingByTag != null) {{
{indent}            chainTo(existingByTag)
{indent}            outboundTagMap["$chainType-$targetRemark"] = desiredTag
{indent}            LogUtil.d(AppConfig.TAG, "Reused existing $chainType outbound: $desiredTag")
{indent}            return
{indent}        }}

{indent}        val mapKey = "$chainType-$targetRemark"
{indent}        val existingTag = outboundTagMap[mapKey]
{indent}        if (existingTag != null) {{
{indent}            val existingOutbound = v2rayConfig.outbounds.firstOrNull {{ it.tag == existingTag }}
{indent}            if (existingOutbound != null) {{
{indent}                chainTo(existingOutbound)
{indent}                LogUtil.d(AppConfig.TAG, "Reused $chainType outbound (map): $existingTag")
{indent}                return
{indent}            }}
{indent}        }}

{indent}        val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return
{indent}        val mainRemarks = MmkvManager.getSelectServer()?.let {{ MmkvManager.decodeServerConfig(it)?.remarks }}
{indent}        if (chainProfile.remarks == mainRemarks) {{
{indent}            outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
{indent}            LogUtil.d(AppConfig.TAG, "Chain $chainType proxy is main server, set dialerProxy to proxy")
{indent}            return
{indent}        }}

{indent}        val chainOutbound = convertProfile2Outbound(chainProfile) ?: return
{indent}        chainOutbound.tag = desiredTag
{indent}        outboundTagMap[mapKey] = desiredTag

{indent}        chainTo(chainOutbound)
{indent}        v2rayConfig.outbounds.add(chainOutbound)
{indent}        existingTags.add(desiredTag)
{indent}        LogUtil.d(AppConfig.TAG, "Created $chainType outbound: $desiredTag")
{indent}    }}

{indent}    addChainOutbound(resolveCurrentServer(subItem.prevProfile), "prev", "$originalTag-prev") {{ prevOutbound ->
{indent}        outbound.ensureSockopt().dialerProxy = prevOutbound.tag
{indent}    }}

{indent}    if (!subItem.nextProfile.isNullOrEmpty()) {{
{indent}        val newOriginalTag = "$originalTag-orig"
{indent}        outbound.tag = newOriginalTag

{indent}        addChainOutbound(resolveCurrentServer(subItem.nextProfile), "next", originalTag) {{ nextOutbound ->
{indent}            nextOutbound.ensureSockopt().dialerProxy = newOriginalTag
{indent}        }}
{indent}    }}
{indent}}}

{indent}/**
{indent} * Injects custom outbounds referenced by routing rules that are not built-in.
{indent} * Also applies prev/next chaining if the profile belongs to a subscription.
{indent} */
{indent}private fun injectCustomOutbounds(v2rayConfig: V2rayConfig) {{
{indent}    val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) {{ it.tag }}
{indent}    val outboundTagMap = mutableMapOf<String, String>()

{indent}    val rulesetItems = MmkvManager.decodeRoutingRulesets() ?: return
{indent}    val customOutboundTags = rulesetItems
{indent}        .filter {{ it.enabled && !AppConfig.BUILTIN_OUTBOUND_TAGS.contains(it.outboundTag) }}
{indent}        .map {{ it.outboundTag }}
{indent}        .distinct()

{indent}    for (tag in customOutboundTags) {{
{indent}        if (tag in existingTags) continue
{indent}        val profile = SettingsManager.getServerViaRemarks(tag) ?: continue
{indent}        val outbound = convertProfile2Outbound(profile) ?: continue
{indent}        outbound.tag = tag

{indent}        applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)

{indent}        v2rayConfig.outbounds.add(outbound)
{indent}        existingTags.add(tag)
{indent}        outboundTagMap[tag] = tag
{indent}        LogUtil.d(AppConfig.TAG, "Injected custom outbound: $tag")
{indent}    }}
{indent}}}
'''
        c = c[:last_brace] + helpers + c[last_brace:]
        print("✓ CoreConfigManager: added helper functions before final '}'")
    else:
        print("• CoreConfigManager: helpers already present")

    # ------------------------------------------------------------------
    # 2. Insert call to injectCustomOutbounds inside buildUnifiedConfig
    #    Insert right before the comment "// User routing rules (...)"
    # ------------------------------------------------------------------
    if "injectCustomOutbounds(v2rayConfig)" not in c:
        marker = "// User routing rules (policyGroupBalancerTags rewrites TAG_PROXY→balancer when main is POLICYGROUP)."
        if marker in c:
            c = c.replace(marker, "        // Inject custom outbounds for routing rules\n        injectCustomOutbounds(v2rayConfig)\n\n        " + marker, 1)
            print("✓ CoreConfigManager: added injectCustomOutbounds call before user routing rules")
        else:
            # Fallback: insert before configureRouting call
            fallback = "configureRouting(configContext, v2rayConfig, policyGroupBalancerTags)"
            if fallback in c:
                c = c.replace(fallback, "        injectCustomOutbounds(v2rayConfig)\n\n        " + fallback, 1)
                print("✓ CoreConfigManager: added injectCustomOutbounds call before configureRouting (fallback)")
            else:
                print("⚠ CoreConfigManager: could not find insertion point for injectCustomOutbounds call")

    write(p, c)
    print("✓ CoreConfigManager: patched successfully")

# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Custom Outbound + Enhanced Profile Selector Patcher (Final Reliable)")
    print("=" * 70)

    files_to_backup = [
        BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt",
        BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt",
        BASE / "app/src/main/res/values/strings.xml",
        BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt",
    ]
    for f in files_to_backup:
        if f.exists():
            backup_kotlin(f)

    try:
        patch_appconfig()
        patch_subedit()
        patch_strings()
        patch_coreconfig()
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild and test – None / [Current Server] in dropdown, custom outbounds with chaining work.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

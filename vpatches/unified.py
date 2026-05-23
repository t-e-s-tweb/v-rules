#!/usr/bin/env python3
"""
Updated patcher for v2rayNG (after May 2026 upstream changes).
- Adds custom outbound injection with prev/next chaining.
- Enhances SubEditActivity dropdown with None and [Current Server].
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

# ── 1. AppConfig.kt (add CURRENT_SERVER if missing) ──────────────────
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

# ── 2. SubEditActivity.kt – enhance dropdown with None / Current Server ──
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found – skipping")
        return
    c = read(p)

    # Ensure imports (AutoCompleteTextView and ArrayAdapter already present)
    # We'll replace the three relevant functions.

    # 2.1 Replace setupProfileRemarkInputs
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
        // Prepend None and [Current Server] to the list
        val suggestions = listOf("None", "[Current Server]") + baseSuggestions

        setupProfileRemarkInput(binding.etPreProfile, binding.btnPreProfileDropdown, suggestions)
        setupProfileRemarkInput(binding.etNextProfile, binding.btnNextProfileDropdown, suggestions)
    }'''

    if old_setup_inputs in c:
        c = c.replace(old_setup_inputs, new_setup_inputs)
        print("✓ SubEditActivity: updated setupProfileRemarkInputs with None and [Current Server]")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInputs not found (maybe already patched)")

    # 2.2 Replace setupProfileRemarkInput to handle mapping on selection
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

        // When an item is selected, map display text to stored value
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
        print("✓ SubEditActivity: updated setupProfileRemarkInput with selection mapping")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInput not found (maybe already patched)")

    # 2.3 Update bindingServer to display friendly strings
    old_binding = '''        binding.etPreProfile.text = Utils.getEditable(subItem.prevProfile)
        binding.etNextProfile.text = Utils.getEditable(subItem.nextProfile)'''
    new_binding = '''        // Convert stored values to display strings
        val preDisplay = when (subItem.prevProfile) {
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
        print("✓ SubEditActivity: updated bindingServer display mapping")
    else:
        print("⚠ SubEditActivity: bindingServer lines not found")

    # 2.4 Update saveServer to convert display back to stored values
    old_save = '''        subItem.prevProfile = binding.etPreProfile.text.toString()
        subItem.nextProfile = binding.etNextProfile.text.toString()'''
    new_save = '''        // Convert display strings back to stored values
        subItem.prevProfile = when (binding.etPreProfile.text.toString()) {
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
        print("✓ SubEditActivity: updated saveServer storage mapping")
    else:
        print("⚠ SubEditActivity: saveServer lines not found")

    write(p, c)
    print("✓ SubEditActivity: all enhancements applied")

# ── 3. strings.xml – add None and [Current Server] if missing ─────────
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

# ── 4. CoreConfigManager.kt – inject custom outbounds with chaining ────
def patch_coreconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found – skipping")
        return
    c = read(p)

    # 4.1 Add helper functions: resolveCurrentServer, applySubscriptionChain, injectCustomOutbounds
    # We'll insert them before the first private fun (e.g., before "private fun buildUnifiedConfig")
    # or at the end of the file. Let's insert after the existing imports and before the object.
    # Actually, we can insert after the object declaration.
    marker = "object CoreConfigManager {"
    if marker not in c:
        print("✗ CoreConfigManager: object declaration not found")
        return

    # Check if already patched
    if "private fun injectCustomOutbounds" in c:
        print("• CoreConfigManager: already patched (injectCustomOutbounds exists)")
        # Still need to ensure the call is in buildUnifiedConfig? We'll try to add call anyway.
    else:
        # Prepare the helper functions block
        helpers = '''

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

            // Check if already added
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

            // Apply chaining if subscriptionId exists
            applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)

            v2rayConfig.outbounds.add(outbound)
            existingTags.add(tag)
            outboundTagMap[tag] = tag
            LogUtil.d(AppConfig.TAG, "Injected custom outbound: $tag")
        }
    }
'''
        # Insert after the object line
        insert_pos = c.index(marker) + len(marker)
        c = c[:insert_pos] + helpers + c[insert_pos:]
        print("✓ CoreConfigManager: added helper functions (resolveCurrentServer, applySubscriptionChain, injectCustomOutbounds)")

    # 4.2 Call injectCustomOutbounds inside buildUnifiedConfig after outbounds are built
    # Find the place after the loop that builds outbounds from resolvedOutbounds.
    # In buildUnifiedConfig, after the forEachIndexed block that calls buildOutbounds, we add a call.
    # We'll look for the line that closes the loop and before configureRouting.
    # Specifically, after the line: "        }" (the end of the forEachIndexed) and before "configureRouting".
    # Use a regex to locate the pattern.
    pattern = r'(        // resolvedOutbounds is a single ordered plan: index 0 is primary and must be prepended,\n        // the rest are routing outbounds and can be appended.\n        configContext.resolvedOutbounds.forEachIndexed { index, spec ->\n            buildOutbounds\(\n                resolvedOutbound = spec,\n                prepend = index == 0,\n                existingTags = existingTags,\n                v2rayConfig = v2rayConfig,\n                policyGroupBalancerTags = policyGroupBalancerTags,\n                balancerStrategies = balancerStrategies,\n            \)\n        }\n)'
    match = re.search(pattern, c, re.DOTALL)
    if match:
        insertion_point = match.end()
        # Insert injectCustomOutbounds right after the closing brace of the loop
        c = c[:insertion_point] + '\n\n        // Inject any custom outbounds referenced by routing rules\n        injectCustomOutbounds(v2rayConfig)\n' + c[insertion_point:]
        print("✓ CoreConfigManager: added injectCustomOutbounds call in buildUnifiedConfig")
    else:
        # Fallback: try to find a simpler pattern
        fallback = "        // User routing rules (policyGroupBalancerTags rewrites TAG_PROXY→balancer when main is POLICYGROUP)."
        if fallback in c:
            c = c.replace(fallback, "        injectCustomOutbounds(v2rayConfig)\n\n        " + fallback)
            print("✓ CoreConfigManager: added injectCustomOutbounds call (fallback)")
        else:
            print("⚠ CoreConfigManager: could not locate insertion point for injectCustomOutbounds call – you may need to manually add it after the outbound building loop in buildUnifiedConfig")

    write(p, c)
    print("✓ CoreConfigManager: patched successfully")

# ── main ──────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Custom Outbound + Enhanced Profile Selector Patcher (Updated for May 2026)")
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
        print("👉 Rebuild and test – None and [Current Server] will appear in dropdown, and custom outbounds will be injected with chain support.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

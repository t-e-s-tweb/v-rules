#!/usr/bin/env python3
import os
import re

def modify_ruleset_item():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/dto/RulesetItem.kt"
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        content = f.read()

    if "var customOutboundTag: String? = null" in content:
        print("  ✓ RulesetItem.kt (already patched)")
        return True

    old = '    var locked: Boolean? = false,'
    new = '    var locked: Boolean? = false,\n    var customOutboundTag: String? = null,'
    if old not in content:
        print("  ✗ Could not find insertion point in RulesetItem.kt")
        return False
    content = content.replace(old, new)
    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ RulesetItem.kt")
    return True

def modify_arrays_xml():
    filepath = "V2rayNG/app/src/main/res/values/arrays.xml"
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        content = f.read()

    if '        <item>custom</item>' in content:
        print("  ✓ arrays.xml (already patched)")
        return True

    old = '        <item>block</item>'
    new = '        <item>block</item>\n        <item>custom</item>'
    if old not in content:
        print("  ✗ Could not find insertion point in arrays.xml")
        return False
    content = content.replace(old, new)
    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ arrays.xml")
    return True

def modify_layout():
    filepath = "V2rayNG/app/src/main/res/layout/activity_routing_edit.xml"
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        content = f.read()

    if 'android:id="@+id/layout_custom_outbound"' in content:
        print("  ✓ activity_routing_edit.xml (already patched)")
        return True

    m = re.search(r'android:entries="@array/outbound_tag" />', content)
    if not m:
        print("  ✗ Could not find spinner in layout")
        return False

    after = content[m.end():]
    cm = re.search(r'(\s*)</LinearLayout>', after)
    if not cm:
        print("  ✗ Could not find parent LinearLayout closing tag")
        return False

    indent = cm.group(1)
    insert_at = m.end() + cm.start()
    end_at = insert_at + len(cm.group(0))

    new_layout = f'''{indent}
{indent}<LinearLayout
{indent}    android:id="@+id/layout_custom_outbound"
{indent}    android:layout_width="match_parent"
{indent}    android:layout_height="wrap_content"
{indent}    android:layout_marginTop="@dimen/padding_spacing_dp16"
{indent}    android:orientation="vertical"
{indent}    android:visibility="gone">
{indent}    <TextView
{indent}        android:layout_width="wrap_content"
{indent}        android:layout_height="wrap_content"
{indent}        android:text="@string/routing_settings_custom_outbound_tag" />
{indent}    <EditText
{indent}        android:id="@+id/et_custom_outbound_tag"
{indent}        android:layout_width="match_parent"
{indent}        android:layout_height="wrap_content"
{indent}        android:inputType="text"
{indent}        android:hint="@string/routing_settings_custom_outbound_hint" />
{indent}</LinearLayout>'''

    content = content[:end_at] + new_layout + content[end_at:]
    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ activity_routing_edit.xml")
    return True

def modify_strings_xml():
    filepath = "V2rayNG/app/src/main/res/values/strings.xml"
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    needed = {
        "routing_settings_custom_outbound_tag": "Custom outbound tag",
        "routing_settings_custom_outbound_hint": "Enter profile/group remark",
        "routing_settings_custom_outbound_empty": "Custom outbound tag cannot be empty"
    }
    changed = False
    for k, v in needed.items():
        if f'name="{k}"' in content:
            continue
        m = re.search(r'(\s*)</resources>', content, re.IGNORECASE)
        if not m:
            print(f"  ✗ Could not find </resources> tag to insert '{k}'")
            return False
        indent = m.group(1)
        pos = m.start()
        content = content[:pos] + f'\n{indent}<string name="{k}">{v}</string>' + content[pos:]
        changed = True
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    print("  ✓ strings.xml")
    return True

def modify_routing_edit_activity():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/ui/RoutingEditActivity.kt"
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        content = f.read()

    # ---- Guard: skip if already fully patched ----
    if "CUSTOM_OUTBOUND_INDEX = 3" in content and "binding.layoutCustomOutbound.visibility" in content:
        print("  ✓ RoutingEditActivity.kt (already patched)")
        return True

    # ---- 1. Add import (if not already) ----
    if "import com.v2ray.ang.extension.isNotNullEmpty" not in content:
        content = content.replace(
            'import com.v2ray.ang.extension.nullIfBlank',
            'import com.v2ray.ang.extension.nullIfBlank\nimport com.v2ray.ang.extension.isNotNullEmpty'
        )

    # ---- 2. Add constant CUSTOM_OUTBOUND_INDEX (if not already) ----
    if "CUSTOM_OUTBOUND_INDEX = 3" not in content:
        pattern = r'(    private val outbound_tag: Array<out String> by lazy {\n        resources\.getStringArray\(R\.array\.outbound_tag\)\n    })'
        replacement = r'''\1
    // Index of "custom" in the outbound_tag array (proxy=0, direct=1, block=2, custom=3)
    private val CUSTOM_OUTBOUND_INDEX = 3'''
        content, n = re.subn(pattern, replacement, content, flags=re.MULTILINE)
        if n == 0:
            print("  ✗ Could not find outbound_tag declaration")
            return False

    # ---- 3. Replace bindingServer with custom-aware version ----
    old_binding = '''    private fun bindingServer(rulesetItem: RulesetItem): Boolean {
        binding.etRemarks.text = Utils.getEditable(rulesetItem.remarks)
        binding.chkLocked.isChecked = rulesetItem.locked == true
        binding.etDomain.text = Utils.getEditable(rulesetItem.domain?.joinToString(","))
        binding.etIp.text = Utils.getEditable(rulesetItem.ip?.joinToString(","))
        binding.etPort.text = Utils.getEditable(rulesetItem.port)
        binding.etProtocol.text = Utils.getEditable(rulesetItem.protocol?.joinToString(","))
        binding.etNetwork.text = Utils.getEditable(rulesetItem.network)
        val outbound = Utils.arrayFind(outbound_tag, rulesetItem.outboundTag)
        binding.spOutboundTag.setSelection(outbound)

        return true
    }'''
    new_binding = '''    private fun bindingServer(rulesetItem: RulesetItem): Boolean {
        binding.etRemarks.text = Utils.getEditable(rulesetItem.remarks)
        binding.chkLocked.isChecked = rulesetItem.locked == true
        binding.etDomain.text = Utils.getEditable(rulesetItem.domain?.joinToString(","))
        binding.etIp.text = Utils.getEditable(rulesetItem.ip?.joinToString(","))
        binding.etPort.text = Utils.getEditable(rulesetItem.port)
        binding.etProtocol.text = Utils.getEditable(rulesetItem.protocol?.joinToString(","))
        binding.etNetwork.text = Utils.getEditable(rulesetItem.network)

        // Check if the outboundTag is one of the standard tags
        val outboundIndex = Utils.arrayFind(outbound_tag, rulesetItem.outboundTag)
        if (outboundIndex == -1) {
            // Custom outbound tag – select "custom" and fill the EditText
            binding.spOutboundTag.setSelection(CUSTOM_OUTBOUND_INDEX)
            binding.etCustomOutboundTag.text = Utils.getEditable(rulesetItem.outboundTag)
            binding.layoutCustomOutbound.visibility = android.view.View.VISIBLE
        } else {
            // Standard tag – select it and clear the custom EditText
            binding.spOutboundTag.setSelection(outboundIndex)
            binding.etCustomOutboundTag.text = null
            binding.layoutCustomOutbound.visibility = android.view.View.GONE
        }

        // Also load the saved customOutboundTag if present (for backward compatibility)
        if (rulesetItem.customOutboundTag.isNotNullEmpty()) {
            binding.etCustomOutboundTag.text = Utils.getEditable(rulesetItem.customOutboundTag)
        }

        return true
    }'''
    # Use flexible whitespace matching to find the old function
    pattern = re.escape(old_binding).replace(r'\ ', r'\s+')
    if not re.search(pattern, content, re.DOTALL):
        print("  ✗ Could not find original bindingServer function")
        return False
    content = re.sub(pattern, new_binding, content, flags=re.DOTALL)

    # ---- 4. Modify clearServer ----
    content = content.replace(
        '        binding.spOutboundTag.setSelection(0)\n        return true',
        '        binding.spOutboundTag.setSelection(0)\n        binding.etCustomOutboundTag.text = null\n        return true'
    )

    # ---- 5. Modify saveServer ----
    if "if (selectedOutboundPosition == CUSTOM_OUTBOUND_INDEX)" not in content:
        content = content.replace(
            '            outboundTag = outbound_tag[binding.spOutboundTag.selectedItemPosition]',
            '''            // Handle custom outbound tag
            val selectedOutboundPosition = binding.spOutboundTag.selectedItemPosition
            if (selectedOutboundPosition == CUSTOM_OUTBOUND_INDEX) {
                val customTag = binding.etCustomOutboundTag.text.toString().trim()
                if (customTag.isEmpty()) {
                    toast(R.string.routing_settings_custom_outbound_empty)
                    return false
                }
                outboundTag = customTag
                customOutboundTag = customTag
            } else {
                outboundTag = outbound_tag[selectedOutboundPosition]
                customOutboundTag = null
            }'''
        )

    # ---- 6. Add spinner listener INSIDE onCreate (before the final '}') ----
    if "binding.spOutboundTag.onItemSelectedListener" not in content:
        # Find the position of the last '}' that closes onCreate
        # We'll locate the function signature and then find the matching closing brace
        # Simpler: find the last '}\n    }' (closes else and then method)
        # Use regex that captures whitespace flexibly
        pattern = r'(\s*)\}\n(\s*)\}'
        # We need to ensure we only replace the very last occurrence
        matches = list(re.finditer(pattern, content))
        if matches:
            last_match = matches[-1]
            start, end = last_match.span()
            indent1 = last_match.group(1)
            indent2 = last_match.group(2)
            # Keep the original closing braces, but insert listener before them
            listener = f'''{indent1}}

        // Setup listener for outbound tag spinner
        binding.spOutboundTag.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {{
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {{
                binding.layoutCustomOutbound.visibility = if (position == CUSTOM_OUTBOUND_INDEX) android.view.View.VISIBLE else android.view.View.GONE
            }}
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {{}}
        }}
    {indent2}}}'''
            content = content[:start] + listener + content[end:]
            print("  ✓ Added spinner listener to onCreate")
        else:
            print("  ✗ Could not find end of onCreate method")
            return False

    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ RoutingEditActivity.kt")
    return True

def modify_v2ray_config_manager():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt"
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        content = f.read()

    # ---- Guard: skip if already fully patched ----
    if "private fun configureCustomOutbound" in content:
        print("  ✓ V2rayConfigManager.kt (already patched)")
        return True

    # ------------------------------------------------------------------
    # 1. Add skip check in getUserRule2Domain
    # ------------------------------------------------------------------
    # Use flexible whitespace pattern
    pattern1 = r'(        if \(key\.enabled && key\.outboundTag == tag && !key\.domain\.isNullOrEmpty\(\) \{)'
    replacement1 = r'''\1
                // Skip custom outbounds - they should not be treated as standard tags
                if (isCustomOutboundTag(key.outboundTag)) return@forEach'''
    content, n1 = re.subn(pattern1, replacement1, content, flags=re.MULTILINE)
    if n1 == 0:
        # Try alternate pattern with possible whitespace variations
        pattern1_alt = r'(\s*if \(key\.enabled && key\.outboundTag == tag && !key\.domain\.isNullOrEmpty\(\) \{)'
        content, n1 = re.subn(pattern1_alt, replacement1, content, flags=re.MULTILINE)
        if n1 == 0:
            print("  ✗ Failed to patch getUserRule2Domain – pattern not found")
            return False

    # ------------------------------------------------------------------
    # 2. Add isCustomOutboundTag method
    # ------------------------------------------------------------------
    pattern2 = r'(        return domain\n    }\n\n    /\*\*)'
    replacement2 = r'''\1

    /**
     * Checks if an outbound tag is a custom (user-defined) outbound.
     * Custom outbounds are those that don't match the standard tags (proxy, direct, block).
     *
     * @param tag The outbound tag to check
     * @return true if the tag is custom, false otherwise
     */
    private fun isCustomOutboundTag(tag: String): Boolean {
        return tag != AppConfig.TAG_PROXY && tag != AppConfig.TAG_DIRECT && tag != AppConfig.TAG_BLOCKED
    }

    /**'''
    content, n2 = re.subn(pattern2, replacement2, content, flags=re.MULTILINE)
    if n2 == 0:
        print("  ✗ Failed to insert isCustomOutboundTag – pattern not found")
        return False

    # ------------------------------------------------------------------
    # 3. Insert configureCustomOutbound + setupChainProxyForOutbound
    #    (Adds custom outbound at INDEX 0)
    # ------------------------------------------------------------------
    pattern3 = r'(        updateOutboundFragment\(v2rayConfig\)\n        return true\n    }\n\n    /\*\*)'
    replacement3 = r'''\1

    /**
     * Configures a custom outbound with chain proxy support.
     * Adds the outbound at the beginning of the list (index 0) so it's defined before routing rules.
     */
    private fun configureCustomOutbound(v2rayConfig: V2rayConfig, customOutboundTag: String): Boolean {
        try {
            Log.i(AppConfig.TAG, "▶️ configureCustomOutbound: $customOutboundTag")
            val profile = SettingsManager.getServerViaRemarks(customOutboundTag)
            if (profile == null) {
                Log.i(AppConfig.TAG, "❌ No profile with remarks '$customOutboundTag'")
                return false
            }
            if (profile.configType == EConfigType.POLICYGROUP) {
                Log.i(AppConfig.TAG, "❌ Policy groups not supported")
                return false
            }
            val outbound = convertProfile2Outbound(profile) ?: run {
                Log.i(AppConfig.TAG, "❌ convertProfile2Outbound failed (type: ${profile.configType})")
                return false
            }
            if (!updateOutboundWithGlobalSettings(outbound)) {
                Log.i(AppConfig.TAG, "❌ updateOutboundWithGlobalSettings failed")
                return false
            }
            outbound.tag = customOutboundTag

            // Add at the beginning of outbounds list so it's available for routing rules
            if (v2rayConfig.outbounds.none { it.tag == customOutboundTag }) {
                v2rayConfig.outbounds.add(0, outbound)
                Log.i(AppConfig.TAG, "✅ Custom outbound added at index 0: $customOutboundTag")
            } else {
                Log.i(AppConfig.TAG, "ℹ️ Custom outbound already exists: $customOutboundTag")
            }

            if (!profile.subscriptionId.isNullOrEmpty()) {
                setupChainProxyForOutbound(v2rayConfig, outbound, profile.subscriptionId)
            }
            return true
        } catch (e: Exception) {
            Log.e(AppConfig.TAG, "❌ Exception in configureCustomOutbound", e)
            return false
        }
    }

    /**
     * Sets up chain proxy (prev/next) for a custom outbound.
     */
    private fun setupChainProxyForOutbound(v2rayConfig: V2rayConfig, outbound: V2rayConfig.OutboundBean, subscriptionId: String) {
        if (subscriptionId.isEmpty()) return
        try {
            val subItem = MmkvManager.decodeSubscription(subscriptionId) ?: return
            val prevNode = SettingsManager.getServerViaRemarks(subItem.prevProfile)
            if (prevNode != null) {
                convertProfile2Outbound(prevNode)?.let { prevOutbound ->
                    updateOutboundWithGlobalSettings(prevOutbound)
                    prevOutbound.tag = "${outbound.tag}-prev"
                    v2rayConfig.outbounds.add(prevOutbound)
                    outbound.ensureSockopt().dialerProxy = prevOutbound.tag
                    Log.i(AppConfig.TAG, "🔗 Prev chain added for ${outbound.tag}")
                }
            }
            val nextNode = SettingsManager.getServerViaRemarks(subItem.nextProfile)
            if (nextNode != null) {
                convertProfile2Outbound(nextNode)?.let { nextOutbound ->
                    updateOutboundWithGlobalSettings(nextOutbound)
                    nextOutbound.tag = "${outbound.tag}-next"
                    v2rayConfig.outbounds.add(0, nextOutbound)
                    val originalTag = outbound.tag
                    outbound.tag = "${originalTag}-orig"
                    nextOutbound.ensureSockopt().dialerProxy = outbound.tag
                    Log.i(AppConfig.TAG, "🔗 Next chain added for ${outbound.tag}")
                }
            }
        } catch (e: Exception) {
            Log.e(AppConfig.TAG, "❌ Chain proxy failed", e)
        }
    }
'''
    content, n3 = re.subn(pattern3, replacement3, content, flags=re.MULTILINE)
    if n3 == 0:
        # Try with flexible whitespace
        pattern3_alt = r'(\s*updateOutboundFragment\(v2rayConfig\)\s*\n\s*return true\s*\n\s*}\s*\n\s*\n\s*/\*\*)'
        content, n3 = re.subn(pattern3_alt, replacement3, content, flags=re.MULTILINE | re.DOTALL)
        if n3 == 0:
            print("  ✗ Failed to insert custom outbound methods – pattern not found")
            return False

    # ------------------------------------------------------------------
    # 4. Rewrite getRouting: configure custom outbounds FIRST, THEN add routing rules
    # ------------------------------------------------------------------
    pattern4 = r'(            val rulesetItems = MmkvManager\.decodeRoutingRulesets\(\)\n            rulesetItems\?\.forEach \{ key ->\n                getRoutingUserRule\(key, v2rayConfig\))'
    replacement4 = r'''            val rulesetItems = MmkvManager.decodeRoutingRulesets()
            val customOutbounds = mutableSetOf<String>()
            rulesetItems?.forEach { key ->
                if (key.enabled && isCustomOutboundTag(key.outboundTag)) {
                    customOutbounds.add(key.outboundTag)
                }
            }
            Log.i(AppConfig.TAG, "🎯 Custom outbound tags: $customOutbounds")
            // Configure custom outbounds BEFORE adding routing rules that reference them
            customOutbounds.forEach { configureCustomOutbound(v2rayConfig, it) }
            // Now add all routing rules
            rulesetItems?.forEach { key ->
                getRoutingUserRule(key, v2rayConfig)
            }'''
    content, n4 = re.subn(pattern4, replacement4, content, flags=re.MULTILINE)
    if n4 == 0:
        # Try with flexible whitespace
        pattern4_alt = r'(\s*val rulesetItems = MmkvManager\.decodeRoutingRulesets\(\)\s*\n\s*rulesetItems\?\.forEach \{ key ->\s*\n\s*getRoutingUserRule\(key, v2rayConfig\))'
        content, n4 = re.subn(pattern4_alt, replacement4, content, flags=re.MULTILINE | re.DOTALL)
        if n4 == 0:
            print("  ✗ Failed to patch getRouting – pattern not found")
            return False

    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ V2rayConfigManager.kt")
    return True

def main():
    print("=" * 70)
    print("Custom Outbound Patcher – Robust & Self‑Aware")
    print("=" * 70)
    results = []
    for name, func in [
        ("RulesetItem.kt", modify_ruleset_item),
        ("arrays.xml", modify_arrays_xml),
        ("activity_routing_edit.xml", modify_layout),
        ("strings.xml", modify_strings_xml),
        ("RoutingEditActivity.kt", modify_routing_edit_activity),
        ("V2rayConfigManager.kt", modify_v2ray_config_manager),
    ]:
        try:
            ok = func()
            results.append((name, ok))
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            results.append((name, False))
    print("=" * 70)
    success = sum(1 for _, ok in results if ok)
    print(f"\n✅ {success}/{len(results)} files patched successfully.")
    if success == len(results):
        print("\n👉 Rebuild the app and test a routing rule with 'custom' outbound.")
        print("   - When creating a new rule, the spinner defaults to 'proxy'.")
        print("   - Select 'custom' from the spinner – the custom input field appears.")
        print("   - Type the EXACT remark of an existing server and save.")
        print("\n📱 Check logcat (filter 'v2rayNG') to confirm:")
        print('   adb logcat -s v2rayNG')
        print("   You should see: 🎯 Custom outbound tags: [...] ✅ Custom outbound added at index 0: ...")
        print("\n   The routing rule will now correctly use the custom outbound.")
    else:
        print("\n❌ Some patches failed – check the error messages above.")

if __name__ == "__main__":
    main()

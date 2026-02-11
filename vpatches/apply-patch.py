#!/usr/bin/env python3
import os
import re

def modify_ruleset_item():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/dto/RulesetItem.kt"
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        content = f.read()
    old = '    var locked: Boolean? = false,'
    new = '    var locked: Boolean? = false,\n    var customOutboundTag: String? = null,'
    if old not in content:
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
    old = '        <item>block</item>'
    new = '        <item>block</item>\n        <item>custom</item>'
    if old not in content:
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
    m = re.search(r'android:entries="@array/outbound_tag" />', content)
    if not m:
        return False
    after = content[m.end():]
    cm = re.search(r'(\s*)</LinearLayout>', after)
    if not cm:
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

    # ---- 1. Add import ----
    content = content.replace(
        'import com.v2ray.ang.extension.nullIfBlank',
        'import com.v2ray.ang.extension.nullIfBlank\nimport com.v2ray.ang.extension.isNotNullEmpty'
    )

    # ---- 2. Add constant CUSTOM_OUTBOUND_INDEX ----
    content = content.replace(
        '    private val outbound_tag: Array<out String> by lazy {\n        resources.getStringArray(R.array.outbound_tag)\n    }',
        '''    private val outbound_tag: Array<out String> by lazy {
        resources.getStringArray(R.array.outbound_tag)
    }
    // Index of "custom" in the outbound_tag array (proxy=0, direct=1, block=2, custom=3)
    private val CUSTOM_OUTBOUND_INDEX = 3'''
    )

    # ---- 3. Modify bindingServer (load custom tag) ----
    content = content.replace(
        '        binding.spOutboundTag.setSelection(outbound)\n\n        return true',
        '''        binding.spOutboundTag.setSelection(outbound)

        // Set custom outbound tag if present
        if (rulesetItem.customOutboundTag.isNotNullEmpty()) {
            binding.etCustomOutboundTag.text = Utils.getEditable(rulesetItem.customOutboundTag)
            // If outboundTag is not in standard list, it might be a custom value
            if (outbound == -1 && rulesetItem.outboundTag.isNotNullEmpty()) {
                binding.etCustomOutboundTag.text = Utils.getEditable(rulesetItem.outboundTag)
            }
        }

        return true'''
    )

    # ---- 4. Modify clearServer (clear custom tag) ----
    content = content.replace(
        '        binding.spOutboundTag.setSelection(0)\n        return true',
        '        binding.spOutboundTag.setSelection(0)\n        binding.etCustomOutboundTag.text = null\n        return true'
    )

    # ---- 5. Modify saveServer (validate and save custom tag) ----
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

    # ---- 6. Replace the end of onCreate: add spinner listener AND pre-fill custom tag ----
    # Original end: "... } else { clearServer() } }"
    # We replace the final "        }\n    }" with a block that contains:
    #   - the else block closing
    #   - the listener
    #   - pre-fill code for new rules
    #   - the method closing brace
    #
    # The exact pattern we need to match is the two closing braces at the end of onCreate:
    #         }   // closes else
    #     }       // closes method
    #
    # We'll capture the indentation before the first } and reuse it.
    pattern = r'(        }\n    })'
    replacement = r'''        }

        // Setup listener for outbound tag spinner
        binding.spOutboundTag.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                binding.layoutCustomOutbound.visibility = if (position == CUSTOM_OUTBOUND_INDEX) android.view.View.VISIBLE else android.view.View.GONE
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }

        // Pre-fill custom outbound tag with the currently selected server's remark for new rules
        if (position == -1) {
            val currentGuid = MmkvManager.getSelectedServer()
            if (currentGuid != null) {
                val currentServer = MmkvManager.decodeServerConfig(currentGuid)
                if (currentServer != null) {
                    binding.etCustomOutboundTag.text = Utils.getEditable(currentServer.remarks)
                }
            }
        }
    }'''
    # Ensure we only replace the very last occurrence
    # Split content, replace last occurrence
    parts = content.rsplit(pattern, 1)
    if len(parts) == 2:
        content = parts[0] + replacement + parts[1]
    else:
        print("  ✗ Failed to patch onCreate end – pattern not found")
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

    if "private fun configureCustomOutbound" in content:
        print("  ✓ V2rayConfigManager.kt (already patched)")
        return True

    # ---- 1. Add skip check in getUserRule2Domain ----
    p1 = r'(        if \(key\.enabled && key\.outboundTag == tag && !key\.domain\.isNullOrEmpty\(\) \{)'
    r1 = r'''\1
                // Skip custom outbounds - they should not be treated as standard tags
                if (isCustomOutboundTag(key.outboundTag)) return@forEach'''
    content = re.sub(p1, r1, content, flags=re.MULTILINE)

    # ---- 2. Add isCustomOutboundTag method ----
    p2 = r'(        return domain\n    }\n\n    /\*\*)'
    r2 = r'''\1

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
    content = re.sub(p2, r2, content, flags=re.MULTILINE)

    # ---- 3. Add configureCustomOutbound + setupChainProxyForOutbound (visible logs) ----
    p3 = r'(        updateOutboundFragment\(v2rayConfig\)\n        return true\n    }\n\n    /\*\*)'
    r3 = r'''\1

    /**
     * Configures a custom outbound with chain proxy support.
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
            if (v2rayConfig.outbounds.none { it.tag == customOutboundTag }) {
                v2rayConfig.outbounds.add(outbound)
                Log.i(AppConfig.TAG, "✅ Custom outbound added: $customOutboundTag")
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

    /**'''
    content = re.sub(p3, r3, content, flags=re.MULTILINE)

    # ---- 4. Modify getRouting: collect and process custom outbounds ----
    p4 = r'(            val rulesetItems = MmkvManager\.decodeRoutingRulesets\(\)\n            rulesetItems\?\.forEach \{ key ->\n                getRoutingUserRule\(key, v2rayConfig\))'
    r4 = r'''            val rulesetItems = MmkvManager.decodeRoutingRulesets()
            val customOutbounds = mutableSetOf<String>()
            rulesetItems?.forEach { key ->
                if (key.enabled && isCustomOutboundTag(key.outboundTag)) {
                    customOutbounds.add(key.outboundTag)
                }
                getRoutingUserRule(key, v2rayConfig)
            }
            Log.i(AppConfig.TAG, "🎯 Custom outbound tags: $customOutbounds")
            customOutbounds.forEach { configureCustomOutbound(v2rayConfig, it) }'''
    content = re.sub(p4, r4, content, flags=re.MULTILINE)

    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ V2rayConfigManager.kt")
    return True

def main():
    print("=" * 70)
    print("Custom Outbound Patcher – Pre‑fills Current Server Remark")
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
        print("\n👉 Rebuild the app and test a new routing rule with 'custom' outbound.")
        print("   The custom outbound tag will be pre‑filled with the currently selected server's remark.")
        print("   Check logcat (filter 'v2rayNG') to confirm the outbound is added.")
    else:
        print("\n❌ Some patches failed – check the error messages above.")

if __name__ == "__main__":
    main()

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
        content = f.read()    if 'android:id="@+id/layout_custom_outbound"' in content:
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
        "routing_settings_custom_outbound_empty": "Custom outbound tag cannot be empty"    }
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

    if "CUSTOM_OUTBOUND_INDEX = 3" in content and "binding.layoutCustomOutbound.visibility" in content:
        print("  ✓ RoutingEditActivity.kt (already patched)")
        return True

    # ---- 1. Add import (check if exists first) ----
    if "import com.v2ray.ang.extension.isNotNullEmpty" not in content:
        if "import com.v2ray.ang.extension.nullIfBlank" in content:
            content = content.replace(
                'import com.v2ray.ang.extension.nullIfBlank',
                'import com.v2ray.ang.extension.nullIfBlank\nimport com.v2ray.ang.extension.isNotNullEmpty'
            )
        else:
            print("  ⚠ nullIfBlank import not found, skipping isNotNullEmpty import")

    # ---- 2. Add constant CUSTOM_OUTBOUND_INDEX ----
    if "CUSTOM_OUTBOUND_INDEX = 3" not in content:
        old_const = '''    private val outbound_tag: Array<out String> by lazy {
        resources.getStringArray(R.array.outbound_tag)
    }'''
        new_const = '''    private val outbound_tag: Array<out String> by lazy {
        resources.getStringArray(R.array.outbound_tag)
    }
    // Index of "custom" in the outbound_tag array (proxy=0, direct=1, block=2, custom=3)
    private val CUSTOM_OUTBOUND_INDEX = 3'''        if old_const not in content:
            print("  ✗ Could not find outbound_tag declaration")
            return False
        content = content.replace(old_const, new_const)

    # ---- 3. Replace bindingServer (Includes etProcess fix) ----
    old_binding = '''    private fun bindingServer(rulesetItem: RulesetItem): Boolean {
        binding.etRemarks.text = Utils.getEditable(rulesetItem.remarks)
        binding.chkLocked.isChecked = rulesetItem.locked == true
        binding.etDomain.text = Utils.getEditable(rulesetItem.domain?.joinToString(","))
        binding.etIp.text = Utils.getEditable(rulesetItem.ip?.joinToString(","))
        binding.etProcess.text = Utils.getEditable(rulesetItem.process?.joinToString(","))
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
        binding.etProcess.text = Utils.getEditable(rulesetItem.process?.joinToString(","))
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

        return true    }'''
    if old_binding not in content:
        print("  ✗ Could not find original bindingServer function")
        return False
    content = content.replace(old_binding, new_binding)

    # ---- 4. Modify clearServer ----
    content = content.replace(
        '        binding.spOutboundTag.setSelection(0)\n        return true',
        '        binding.spOutboundTag.setSelection(0)\n        binding.etCustomOutboundTag.text = null\n        return true'
    )

    # ---- 5. Modify saveServer ----
    if "if (selectedOutboundPosition == CUSTOM_OUTBOUND_INDEX)" not in content:
        old_save = '            outboundTag = outbound_tag[binding.spOutboundTag.selectedItemPosition]'
        new_save = '''            // Handle custom outbound tag
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
        if old_save not in content:
            print("  ✗ Could not find saveServer assignment")
            return False
        content = content.replace(old_save, new_save)

    # ---- 6. Insert spinner listener INSIDE onCreate ----
    if "binding.spOutboundTag.onItemSelectedListener" not in content:
        old_end = '        }\n    }'
        if old_end not in content:
            print("  ✗ Could not find end of onCreate")
            return False
        listener = '''        }

        // Setup listener for outbound tag spinner
        binding.spOutboundTag.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                binding.layoutCustomOutbound.visibility = if (position == CUSTOM_OUTBOUND_INDEX) android.view.View.VISIBLE else android.view.View.GONE
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
    }'''        content = content.replace(old_end, listener)

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

    # ------------------------------------------------------------------
    # 1. Patch getUserRule2Domain – skip custom outbounds
    # ------------------------------------------------------------------
    old_getUserRule = '        if (key.enabled && key.outboundTag == tag && !key.domain.isNullOrEmpty()) {'
    new_getUserRule = '''        if (key.enabled && key.outboundTag == tag && !key.domain.isNullOrEmpty()) {
                // Skip custom outbounds - they should not be treated as standard tags
                if (isCustomOutboundTag(key.outboundTag)) return@forEach'''
    if old_getUserRule not in content:
        print("  ✗ Failed to patch getUserRule2Domain – exact line not found")
        return False
    content = content.replace(old_getUserRule, new_getUserRule, 1)

    # ------------------------------------------------------------------
    # 2. Insert isCustomOutboundTag
    # ------------------------------------------------------------------
    old_anchor = '''        return domain
    }

    /**'''
    new_anchor = '''        return domain
    }

    /**
     * Checks if an outbound tag is a custom (user-defined) outbound.
     */
    private fun isCustomOutboundTag(tag: String): Boolean {
        return tag != AppConfig.TAG_PROXY && tag != AppConfig.TAG_DIRECT && tag != AppConfig.TAG_BLOCKED
    }

    /**'''
    if old_anchor not in content:
        print("  ✗ Failed to insert isCustomOutboundTag – anchor not found")        return False
    content = content.replace(old_anchor, new_anchor, 1)

    # ------------------------------------------------------------------
    # 3. Insert configureCustomOutbound + setupChainProxyForOutbound
    # ------------------------------------------------------------------
    insert_before = '    private fun getMoreOutbounds('
    if insert_before not in content:
        print("  ✗ Failed to find getMoreOutbounds anchor")
        return False

    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.strip().startswith('private fun getMoreOutbounds('):
            new_methods = '''
    /**
     * Configures a custom outbound with chain proxy support.
     */
    private fun configureCustomOutbound(v2rayConfig: V2rayConfig, customOutboundTag: String): Boolean {
        try {
            LogUtil.i(AppConfig.TAG, "▶️ configureCustomOutbound: $customOutboundTag")
            val profile = SettingsManager.getServerViaRemarks(customOutboundTag)
            if (profile == null) {
                LogUtil.i(AppConfig.TAG, "❌ No profile with remarks '$customOutboundTag'")
                return false
            }
            if (profile.configType == EConfigType.POLICYGROUP) {
                LogUtil.i(AppConfig.TAG, "❌ Policy groups not supported")
                return false
            }
            val outbound = convertProfile2Outbound(profile) ?: run {
                LogUtil.i(AppConfig.TAG, "❌ convertProfile2Outbound failed (type: ${profile.configType})")
                return false
            }
            if (!updateOutboundWithGlobalSettings(outbound)) {
                LogUtil.i(AppConfig.TAG, "❌ updateOutboundWithGlobalSettings failed")
                return false
            }
            outbound.tag = customOutboundTag

            // Add at the beginning of outbounds list
            if (v2rayConfig.outbounds.none { it.tag == customOutboundTag }) {
                v2rayConfig.outbounds.add(0, outbound)
                LogUtil.i(AppConfig.TAG, "✅ Custom outbound added at index 0: $customOutboundTag")
            } else {
                LogUtil.i(AppConfig.TAG, "ℹ️ Custom outbound already exists: $customOutboundTag")
            }

            if (!profile.subscriptionId.isNullOrEmpty()) {
                setupChainProxyForOutbound(v2rayConfig, outbound, profile.subscriptionId)            }
            return true
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "❌ Exception in configureCustomOutbound", e)
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
                    LogUtil.i(AppConfig.TAG, "🔗 Prev chain added for ${outbound.tag}")
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
                    LogUtil.i(AppConfig.TAG, "🔗 Next chain added for ${outbound.tag}")
                }
            }
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "❌ Chain proxy failed", e)
        }
    }
'''
            lines.insert(i, new_methods)
            content = '\n'.join(lines)
            print("  ✓ Inserted custom outbound methods before getMoreOutbounds")
            break

    # ------------------------------------------------------------------
    # 4. Patch getRouting – (Includes 'context' parameter fix)
    # ------------------------------------------------------------------    old_getRouting = '''            val rulesetItems = MmkvManager.decodeRoutingRulesets()
            rulesetItems?.forEach { key ->
                getRoutingUserRule(context, key, v2rayConfig)'''
    new_getRouting = '''            val rulesetItems = MmkvManager.decodeRoutingRulesets()
            val customOutbounds = mutableSetOf<String>()
            rulesetItems?.forEach { key ->
                if (key.enabled && isCustomOutboundTag(key.outboundTag)) {
                    customOutbounds.add(key.outboundTag)
                }
            }
            LogUtil.i(AppConfig.TAG, "🎯 Custom outbound tags: $customOutbounds")
            // Configure custom outbounds BEFORE adding routing rules that reference them
            customOutbounds.forEach { configureCustomOutbound(v2rayConfig, it) }
            // Now add all routing rules
            rulesetItems?.forEach { key ->
                getRoutingUserRule(context, key, v2rayConfig)'''
    if old_getRouting not in content:
        print("  ✗ Failed to patch getRouting – exact block not found")
        return False
    content = content.replace(old_getRouting, new_getRouting, 1)

    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ V2rayConfigManager.kt")
    return True

def main():
    print("=" * 70)
    print("Custom Outbound Patcher – Fixed")
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
        print("\n👉 Rebuild the app and test.")    else:
        print("\n❌ Some patches failed.")

if __name__ == "__main__":
    main()

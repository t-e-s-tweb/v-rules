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
        lines = f.readlines()

    # Check if already patched
    content = ''.join(lines)
    if "CUSTOM_OUTBOUND_INDEX = 3" in content and "binding.layoutCustomOutbound.visibility" in content:
        print("  ✓ RoutingEditActivity.kt (already patched)")
        return True

    # 1. Add import for isNotNullEmpty (if not present)
    import_idx = None
    for i, line in enumerate(lines):
        if 'import com.v2ray.ang.extension.nullIfBlank' in line:
            import_idx = i
            break
    if import_idx is not None:
        # Check if already imported
        if not any('import com.v2ray.ang.extension.isNotNullEmpty' in l for l in lines):
            lines.insert(import_idx + 1, 'import com.v2ray.ang.extension.isNotNullEmpty\n')

    # 2. Add CUSTOM_OUTBOUND_INDEX constant after outbound_tag lazy init
    for i, line in enumerate(lines):
        if 'private val outbound_tag: Array<out String> by lazy {' in line:
            # find the closing brace of the lazy block
            brace_count = 0
            found_start = False
            end_idx = i
            for j in range(i, len(lines)):
                if '{' in lines[j]:
                    found_start = True
                    brace_count += lines[j].count('{')
                if '}' in lines[j]:
                    brace_count -= lines[j].count('}')
                if found_start and brace_count == 0:
                    end_idx = j
                    break
            # Insert constant after the lazy block
            indent = re.match(r'(\s*)', lines[end_idx]).group(1)
            lines.insert(end_idx + 1, f'\n{indent}// Index of "custom" in the outbound_tag array (proxy=0, direct=1, block=2, custom=3)\n')
            lines.insert(end_idx + 2, f'{indent}private val CUSTOM_OUTBOUND_INDEX = 3\n')
            break

    # 3. Modify bindingServer function
    # Locate the function and replace body
    func_start = None
    func_end = None
    for i, line in enumerate(lines):
        if 'private fun bindingServer(rulesetItem: RulesetItem): Boolean {' in line:
            func_start = i
            break
    if func_start is not None:
        # find matching closing brace
        brace_count = 0
        found_start = False
        for j in range(func_start, len(lines)):
            if '{' in lines[j]:
                found_start = True
                brace_count += lines[j].count('{')
            if '}' in lines[j]:
                brace_count -= lines[j].count('}')
            if found_start and brace_count == 0:
                func_end = j
                break
        if func_end:
            # Build new function body
            indent = re.match(r'(\s*)', lines[func_start]).group(1)
            new_func = f'''{indent}private fun bindingServer(rulesetItem: RulesetItem): Boolean {{
{indent}    binding.etRemarks.text = Utils.getEditable(rulesetItem.remarks)
{indent}    binding.chkLocked.isChecked = rulesetItem.locked == true
{indent}    binding.etDomain.text = Utils.getEditable(rulesetItem.domain?.joinToString(","))
{indent}    binding.etIp.text = Utils.getEditable(rulesetItem.ip?.joinToString(","))
{indent}    binding.etProcess.text = Utils.getEditable(rulesetItem.process?.joinToString(","))
{indent}    binding.etPort.text = Utils.getEditable(rulesetItem.port)
{indent}    binding.etProtocol.text = Utils.getEditable(rulesetItem.protocol?.joinToString(","))
{indent}    binding.etNetwork.text = Utils.getEditable(rulesetItem.network)

{indent}    // Check if the outboundTag is one of the standard tags
{indent}    val outboundIndex = Utils.arrayFind(outbound_tag, rulesetItem.outboundTag)
{indent}    if (outboundIndex == -1) {{
{indent}        // Custom outbound tag – select "custom" and fill the EditText
{indent}        binding.spOutboundTag.setSelection(CUSTOM_OUTBOUND_INDEX)
{indent}        binding.etCustomOutboundTag.text = Utils.getEditable(rulesetItem.outboundTag)
{indent}        binding.layoutCustomOutbound.visibility = android.view.View.VISIBLE
{indent}    }} else {{
{indent}        // Standard tag – select it and clear the custom EditText
{indent}        binding.spOutboundTag.setSelection(outboundIndex)
{indent}        binding.etCustomOutboundTag.text = null
{indent}        binding.layoutCustomOutbound.visibility = android.view.View.GONE
{indent}    }}

{indent}    // Also load the saved customOutboundTag if present (for backward compatibility)
{indent}    if (rulesetItem.customOutboundTag.isNotNullEmpty()) {{
{indent}        binding.etCustomOutboundTag.text = Utils.getEditable(rulesetItem.customOutboundTag)
{indent}    }}

{indent}    return true
{indent}}}'''
            # Replace from func_start to func_end
            lines[func_start:func_end+1] = [new_func + '\n']

    # 4. Modify clearServer
    for i, line in enumerate(lines):
        if 'binding.spOutboundTag.setSelection(0)' in line and 'clearServer' in ''.join(lines[max(0,i-5):i+5]):
            indent = re.match(r'(\s*)', line).group(1)
            lines[i] = f'{indent}binding.spOutboundTag.setSelection(0)\n'
            lines.insert(i+1, f'{indent}binding.etCustomOutboundTag.text = null\n')
            break

    # 5. Modify saveServer to handle custom outbound
    # Find the outboundTag assignment line
    for i, line in enumerate(lines):
        if 'outboundTag = outbound_tag[binding.spOutboundTag.selectedItemPosition]' in line:
            indent = re.match(r'(\s*)', line).group(1)
            new_block = f'''{indent}// Handle custom outbound tag
{indent}val selectedOutboundPosition = binding.spOutboundTag.selectedItemPosition
{indent}if (selectedOutboundPosition == CUSTOM_OUTBOUND_INDEX) {{
{indent}    val customTag = binding.etCustomOutboundTag.text.toString().trim()
{indent}    if (customTag.isEmpty()) {{
{indent}        toast(R.string.routing_settings_custom_outbound_empty)
{indent}        return false
{indent}    }}
{indent}    outboundTag = customTag
{indent}    customOutboundTag = customTag
{indent}}} else {{
{indent}    outboundTag = outbound_tag[selectedOutboundPosition]
{indent}    customOutboundTag = null
{indent}}}'''
            lines[i:i+1] = [new_block + '\n']
            break

    # 6. Add spinner listener inside onCreate
    # Find the end of onCreate (line with '    }' after onCreate definition)
    in_on_create = False
    brace_count = 0
    for i, line in enumerate(lines):
        if 'override fun onCreate(' in line:
            in_on_create = True
            continue
        if in_on_create:
            brace_count += line.count('{')
            brace_count -= line.count('}')
            if brace_count == 0 and '}' in line and line.strip() == '}':
                # This is the closing brace of onCreate
                indent = re.match(r'(\s*)', line).group(1)
                listener_code = f'''{indent}
{indent}    // Setup listener for outbound tag spinner
{indent}    binding.spOutboundTag.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {{
{indent}        override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {{
{indent}            binding.layoutCustomOutbound.visibility = if (position == CUSTOM_OUTBOUND_INDEX) android.view.View.VISIBLE else android.view.View.GONE
{indent}        }}
{indent}        override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {{}}
{indent}    }}
{indent}}}'''
                lines.insert(i, listener_code)
                break

    with open(filepath, 'w') as f:
        f.writelines(lines)
    print("  ✓ RoutingEditActivity.kt")
    return True

def modify_v2ray_config_manager():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt"
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        lines = f.readlines()

    content = ''.join(lines)
    if "private fun configureCustomOutbound" in content:
        print("  ✓ V2rayConfigManager.kt (already patched)")
        return True

    # 1. Patch getUserRule2Domain to skip custom outbounds
    for i, line in enumerate(lines):
        if 'if (key.enabled && key.outboundTag == tag && !key.domain.isNullOrEmpty()) {' in line:
            indent = re.match(r'(\s*)', line).group(1)
            lines.insert(i+1, f'{indent}    // Skip custom outbounds - they should not be treated as standard tags\n')
            lines.insert(i+2, f'{indent}    if (isCustomOutboundTag(key.outboundTag)) return@forEach\n')
            break

    # 2. Insert isCustomOutboundTag function before "    private fun getCustomLocalDns"
    for i, line in enumerate(lines):
        if 'private fun getCustomLocalDns(' in line:
            indent = re.match(r'(\s*)', line).group(1)
            func_code = f'''
{indent}/**
{indent} * Checks if an outbound tag is a custom (user-defined) outbound.
{indent} * Custom outbounds are those that don't match the standard tags (proxy, direct, block).
{indent} */
{indent}private fun isCustomOutboundTag(tag: String): Boolean {{
{indent}    return tag != AppConfig.TAG_PROXY && tag != AppConfig.TAG_DIRECT && tag != AppConfig.TAG_BLOCKED
{indent}}}

'''
            lines.insert(i, func_code)
            break

    # 3. Insert configureCustomOutbound and setupChainProxyForOutbound before getMoreOutbounds
    for i, line in enumerate(lines):
        if 'private fun getMoreOutbounds(' in line:
            indent = re.match(r'(\s*)', line).group(1)
            new_methods = f'''
{indent}/**
{indent} * Configures a custom outbound with chain proxy support.
{indent} * Adds the outbound at the beginning of the list (index 0) so it's defined before routing rules.
{indent} */
{indent}private fun configureCustomOutbound(v2rayConfig: V2rayConfig, customOutboundTag: String): Boolean {{
{indent}    try {{
{indent}        LogUtil.i(AppConfig.TAG, "▶️ configureCustomOutbound: $customOutboundTag")
{indent}        val profile = SettingsManager.getServerViaRemarks(customOutboundTag)
{indent}        if (profile == null) {{
{indent}            LogUtil.i(AppConfig.TAG, "❌ No profile with remarks '$customOutboundTag'")
{indent}            return false
{indent}        }}
{indent}        if (profile.configType == EConfigType.POLICYGROUP) {{
{indent}            LogUtil.i(AppConfig.TAG, "❌ Policy groups not supported")
{indent}            return false
{indent}        }}
{indent}        val outbound = convertProfile2Outbound(profile) ?: run {{
{indent}            LogUtil.i(AppConfig.TAG, "❌ convertProfile2Outbound failed (type: ${{profile.configType}})")
{indent}            return false
{indent}        }}
{indent}        if (!updateOutboundWithGlobalSettings(outbound)) {{
{indent}            LogUtil.i(AppConfig.TAG, "❌ updateOutboundWithGlobalSettings failed")
{indent}            return false
{indent}        }}
{indent}        outbound.tag = customOutboundTag

{indent}        // Add at the beginning of outbounds list so it's available for routing rules
{indent}        if (v2rayConfig.outbounds.none {{ it.tag == customOutboundTag }}) {{
{indent}            v2rayConfig.outbounds.add(0, outbound)
{indent}            LogUtil.i(AppConfig.TAG, "✅ Custom outbound added at index 0: $customOutboundTag")
{indent}        }} else {{
{indent}            LogUtil.i(AppConfig.TAG, "ℹ️ Custom outbound already exists: $customOutboundTag")
{indent}        }}

{indent}        if (!profile.subscriptionId.isNullOrEmpty()) {{
{indent}            setupChainProxyForOutbound(v2rayConfig, outbound, profile.subscriptionId)
{indent}        }}
{indent}        return true
{indent}    }} catch (e: Exception) {{
{indent}        LogUtil.e(AppConfig.TAG, "❌ Exception in configureCustomOutbound", e)
{indent}        return false
{indent}    }}
{indent}}}

{indent}/**
{indent} * Sets up chain proxy (prev/next) for a custom outbound.
{indent} */
{indent}private fun setupChainProxyForOutbound(v2rayConfig: V2rayConfig, outbound: V2rayConfig.OutboundBean, subscriptionId: String) {{
{indent}    if (subscriptionId.isEmpty()) return
{indent}    try {{
{indent}        val subItem = MmkvManager.decodeSubscription(subscriptionId) ?: return
{indent}        val prevNode = SettingsManager.getServerViaRemarks(subItem.prevProfile)
{indent}        if (prevNode != null) {{
{indent}            convertProfile2Outbound(prevNode)?.let {{ prevOutbound ->
{indent}                updateOutboundWithGlobalSettings(prevOutbound)
{indent}                prevOutbound.tag = "${{outbound.tag}}-prev"
{indent}                v2rayConfig.outbounds.add(prevOutbound)
{indent}                outbound.ensureSockopt().dialerProxy = prevOutbound.tag
{indent}                LogUtil.i(AppConfig.TAG, "🔗 Prev chain added for ${{outbound.tag}}")
{indent}            }}
{indent}        }}
{indent}        val nextNode = SettingsManager.getServerViaRemarks(subItem.nextProfile)
{indent}        if (nextNode != null) {{
{indent}            convertProfile2Outbound(nextNode)?.let {{ nextOutbound ->
{indent}                updateOutboundWithGlobalSettings(nextOutbound)
{indent}                nextOutbound.tag = "${{outbound.tag}}-next"
{indent}                v2rayConfig.outbounds.add(0, nextOutbound)
{indent}                val originalTag = outbound.tag
{indent}                outbound.tag = "${{originalTag}}-orig"
{indent}                nextOutbound.ensureSockopt().dialerProxy = outbound.tag
{indent}                LogUtil.i(AppConfig.TAG, "🔗 Next chain added for ${{outbound.tag}}")
{indent}            }}
{indent}        }}
{indent}    }} catch (e: Exception) {{
{indent}        LogUtil.e(AppConfig.TAG, "❌ Chain proxy failed", e)
{indent}    }}
{indent}}}

'''
            lines.insert(i, new_methods)
            break

    # 4. Patch getRouting to collect and configure custom outbounds
    # Find the line with "val rulesetItems = MmkvManager.decodeRoutingRulesets()"
    for i, line in enumerate(lines):
        if 'val rulesetItems = MmkvManager.decodeRoutingRulesets()' in line:
            # Find the next line with "rulesetItems?.forEach"
            for j in range(i+1, min(i+10, len(lines))):
                if 'rulesetItems?.forEach' in lines[j]:
                    indent = re.match(r'(\s*)', lines[j]).group(1)
                    insertion = f'''{indent}// Collect custom outbound tags from enabled rules
{indent}val customOutbounds = mutableSetOf<String>()
{indent}rulesetItems?.forEach {{ key ->
{indent}    if (key.enabled && isCustomOutboundTag(key.outboundTag)) {{
{indent}        customOutbounds.add(key.outboundTag)
{indent}    }}
{indent}}}
{indent}LogUtil.i(AppConfig.TAG, "🎯 Custom outbound tags: $customOutbounds")
{indent}// Configure custom outbounds before adding routing rules
{indent}customOutbounds.forEach {{ configureCustomOutbound(v2rayConfig, it) }}
'''
                    lines.insert(j, insertion)
                    break
            break

    with open(filepath, 'w') as f:
        f.writelines(lines)
    print("  ✓ V2rayConfigManager.kt")
    return True

def main():
    print("=" * 70)
    print("Custom Outbound Patcher – Updated for latest v2rayNG")
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
    else:
        print("\n❌ Some patches failed – check the error messages above.")

if __name__ == "__main__":
    main()

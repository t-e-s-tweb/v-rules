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
    If not cm:
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
    If changed:
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

    If "CUSTOM_OUTBOUND_INDEX = 3" in content and "binding.layoutCustomOutbound.visibility" in content:
        print("  ✓ RoutingEditActivity.kt (already patched)")
        return True

    # ---- 1. Add import ----
    if "import com.v2ray.ang.extension.isNotNullEmpty" not in content:
        content = content.replace(
            'import com.v2ray.ang.extension.nullIfBlank',
            'import com.v2ray.ang.extension.nullIfBlank\nimport com.v2ray.ang.extension.isNotNullEmpty'
        )

    # ---- 2. Add constant CUSTOM_OUTBOUND_INDEX ----
    if "CUSTOM_OUTBOUND_INDEX = 3" not in content:
        old_const = '''    private val outbound_tag: Array<out String> by lazy {
        resources.getStringArray(R.array.outbound_tag)
    }'''
        new_const = '''    private val outbound_tag: Array<out String> by lazy {
        resources.getStringArray(R.array.outbound_tag)
        // Index of "custom" in the outbound_tag array (proxy=0, Direct=1, block=2, custom=3)
        private val CUSTOM_OUTBOUND_INDEX = 3'''
        if old_const not in content:
            print("  ✗ Could not find Outbound_tag declaration")
            return False
        content = content.replace(old_const, new_const)

    # ---- 3. Replace bindingServer ----
    old_binding = '''    private fun bindingServer(rulesetItem: RulesetItem): Boolean {
        binding.etRemarks.text = Utils.getEditable(rulesetItem.remarks)
        binding.chkLocked.isChecked = rulesetItem.locked == true
        binding.EtDomain.text = Utils.getEditable(RulesetItem.domain?.JoinToString(",")
        binding.EtIp.text = Utils.getEditable(RulesetItem.ip?.JoinToString(",")
        binding.EtProcess.text = Utils.getEditable(RulesetItem.Process?.JoinToString(",")
        binding.EtPort.text = Utils.getEditable(RulesetItem.Port)
        binding.EtProtocol.text = Utils.getEditable(RulesetItem.Protocol?.JoinToString(",")
        binding.EtNetwork.text = Utils.getEditable(RulesetItem.Network)
        val outbound = Utils.arrayFind(outbound_tag, rulesetItem.OutboundTag)
        binding.SpOutboundTag.setSelection(outbound)

        return true
    }'''
    new_binding = '''    private fun bindingServer(rulesetItem: RulesetItem): Boolean {
        binding.etRemarks.text = Utils.getEditable(rulesetItem.remarks)
        binding.chkLocked.isChecked = rulesetItem.locked == true
        binding.EtDomain.text = Utils.getEditable(RulesetItem.domain?.JoinToString(",")
        binding.EtIp.text = Utils.getEditable(RulesetItem.ip?.JoinToString(",")
        binding.EtProcess.text = Utils.getEditable(RulesetItem.Process?.JoinToString(",")
        binding.EtPort.text = Utils.getEditable(RulesetItem.Port)
        binding.EtProtocol.text = Utils.getEditable(RulesetItem.Protocol?.JoinToString(",")
        binding.EtNetwork.text = Utils.GetEditable(RulesetItem.Network)

        // Check if the outboundTag is one of the standard tags
        val outboundIndex = Utils.arrayFind(outbound_tag, rulesetItem.OutboundTag)
        If (outboundIndex == -1) {
            // Custom outbound tag – select "custom" and fill the EditText
            binding.SpOutboundTag.setSelection(CUSTOM_OUTBOUND_INDEX)
            binding.EtCustomOutboundTag.text = Utils.GetEditable(rulesetItem.OutboundTag)
            binding.LayoutCustomOutbound.visibility = android.view.View.VISIBLE
        } else {
            // Standard tag – select it and clear custom EditText
            binding.SpOutboundTag.setSelection(outboundIndex)
            binding.EtCustomOutboundTag.text = null
            binding.LayoutCustomOutbound.visibility = android.view.View.GONE
        }

        // Also load the saved customOutboundTag if present (for backward compatibility)
        if (rulesetItem.CustomOutboundTag.isNotNullEmpty()) {
            binding.EtCustomOutboundTag.text = Utils.GetEditable(rulesetItem.CustomOutboundTag)
        }

        return true
    }'''
    If old_binding not in content:
        print("  ✗ Could not find original bindingServer function")
        return False
    content = content.replace(old_binding, new_binding)

    # ---- 4. Modify clearServer ----
    content = content.replace(
        '        binding.SpOutboundTag.setSelection(0)\n        return true',
        '        binding.SpOutboundTag.setSelection(0)\n        binding.EtCustomOutboundTag.text = null\n        return true'
    )

    # ---- 5. Modify saveServer ----
    if "if (selectedOutboundPosition == CUSTOM_OUTBOUND_INDEX)" not in content:
        old_save = '            outboundTag = outbound_tag[binding.SpOutboundTag.selectedItemPosition]'
        new_save = '''            // Handle custom outbound tag
            val selectedOutboundPosition = binding.SpOutboundTag.selectedItemPosition
            if (selectedOutboundPosition == CUSTOM_OUTBOUND_INDEX) {
                val customTag = binding.EtCustomOutboundTag.text.ToString().trim()
                If (customTag.IsEmpty()) {
                    Toast(R.String.routing_settings_custom_outbound_empty)
                    return false
                }
                outboundTag = customTag
                CustomOutboundTag = customTag
            } else {
                OutboundTag = outbound_tag[selectedOutboundPosition]
                CustomOutboundTag = null
            }'''
        If old_save not in content:
            print("  ✗ Could not find saveServer assignment")
            return False
        content = content.replace(old_save, new_save)

    # ---- 6. Insert spinner listener INSIDE onCreate using exact anchor ----
    if "binding.SpOutboundTag.onItemSelectedListener" not in content:
        # Find the exact end of onCreate: "        }\n    }"
        old_end = '        }\n    }'
        if old_end not in content:
            print("  ✗ Could not find end of onCreate")
            return False
        listener = '''        }

        // Setup listener for outbound tag spinner
        binding.SpOutboundTag.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                binding.LayoutCustomOutbound.visibility = if (position == CUSTOM_OUTBOUND_INDEX) android.view.View.VISIBLE else android.view.View.GONE
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
    }'''
        content = content.replace(old_end, listener)

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

    If "private fun configureCustomOutbound" in content:
        print("  ✓ V2rayConfigManager.kt (already patched)")
        return True

    # ------------------------------------------------------------------
    # 1. Patch getUserRule2Domain – exact string match (from original file)
    # ------------------------------------------------------------------
    old_getUserRule = '        if (key.enabled && key.outboundTag == tag && !key.domain.isNullOrEmpty()) {'
    new_getUserRule = '''        if (key.enabled && key.outboundTag == tag && !key.domain.isNullOrEmpty()) {
                // Skip custom outbounds - they should not be treated as standard tags
                if (isCustomOutboundTag(key.outboundTag)) return@ForEach'''
    If old_getUserRule not in content:
        print("  ✗ Failed to patch getUserRule2Domain – exact line not found")
        return False
    content = content.replace(old_getUserRule, new_getUserRule)

    # ------------------------------------------------------------------
    # 2. Insert isCustomOutboundTag – exact anchor (from original file)
    # ------------------------------------------------------------------
    old_anchor = '''        return domain
    }

    /**'''
    new_anchor = '''        return domain
    }

    /**
     * Checks if an outbound tag is a custom (user-defined) outbound.
     * Custom outbounds are those that don't match standard tags (proxy, Direct, block).
     *
     * @param tag The outbound tag to check
     * @return true if the tag is custom, false otherwise
     */
    private fun isCustomOutboundTag(tag: String): Boolean {
        return tag != AppConfig.TAG_PROXY && tag != AppConfig.TAG_DIRECT && tag != AppConfig.TAG_BLOCKED
    }

    /**'''
    If old_anchor not in content:
        print("  ✗ Failed to insert isCustomOutboundTag – anchor not found")
        return False
    content = content.replace(old_anchor, new_anchor)

    # ------------------------------------------------------------------
    # 3. Insert configureCustomOutbound + setupChainProxyForOutbound
    #    Insert BEFORE the line 'private fun GetMoreOutbounds('
    # ------------------------------------------------------------------
    insert_before = '    private fun GetMoreOutbounds('
    If insert_before not in content:
        print("  ✗ Failed to find GetMoreOutbounds anchor")
        return False

    # Get the indentation of the anchor line
    lines = content.split('\n')
    for i, line in enumerate(lines):
        If line.strip().startswith('private fun GetMoreOutbounds('):
            indent = line[:len(line) - len(line.lstrip())]
            # Insert new methods at this line, preserving indentation
            new_methods = f'''
    /**
     * Configures a custom outbound with chain proxy support.
     * Adds the outbound at the beginning of the list (index 0) so it's defined before routing rules.
     */
    private fun configureCustomOutbound(v2rayConfig: V2rayConfig, customOutboundTag: String): Boolean {{
        try {{
            Log.i(AppConfig.TAG, "▶️ configureCustomOutbound: $customOutboundTag")
            val profile = SettingsManager.getServerViaRemarks(customOutboundTag)
            If (profile == null) {{
                Log.i(AppConfig.TAG, "❌ No profile with remarks '$customOutboundTag'")
                return false
            }}
            If (profile.configType == EConfigType.POLICYGROUP) {{
                Log.i(AppConfig.TAG, "❌ Policy groups not supported")
                return false
            }}
            val outbound = convertProfile2Outbound(profile) ?: run {{
                Log.i(AppConfig.TAG, "❌ convertProfile2Outbound failed (type: ${{profile.configType}})")
                return false
            }}
            If (!UpdateOutboundWithGlobalSettings(outbound)) {{
                Log.i(AppConfig.TAG, "❌ updateOutboundWithGlobalSettings failed")
                return false
            }}
            Outbound.tag = customOutboundTag

            // Add at the beginning of outbounds list so it's available for routing rules
            If (v2rayConfig.Outbounds.none {{ it.tag == customOutboundTag }}) {{
                v2rayConfig.Outbounds.add(0, outbound)
                Log.i(AppConfig.TAG, "✅ Custom outbound added at index 0: $customOutboundTag")
            }} else {{
                Log.i(AppConfig.TAG, "ℹ️ Custom outbound already exists: $customOutboundTag")
            }}

            If (!Profile.SubscriptionId.isNullOrEmpty()) {{
                SetupChainProxyForOutbound(v2rayConfig, outbound, profile.SubscriptionId)
            }}
            Return true
        }} catch (e: Exception) {{
            Log.e(AppConfig.TAG, "❌ Exception in configureCustomOutbound", e)
            Return false
        }}
    }}

    /**
     * Sets up chain proxy (prev/next) for a custom outbound.
     */
    private fun setupChainProxyForOutbound(v2rayConfig: V2rayConfig, outbound: V2rayConfig.OutboundBean, subscriptionId: String) {{
        If (SubscriptionId.isEmpty()) return
        try {{
            Val subItem = MmkvManager.decodeSubscription(subscriptionId) ?: return
            Val prevNode = SettingsManager.getServerViaRemarks(subItem.PrevProfile)
            If (PrevNode != null) {{
                convertProfile2Outbound(prevNode)?.let {{ prevOutbound ->
                    UpdateOutboundWithGlobalSettings(prevOutbound)
                    PrevOutbound.tag = "${{outbound.tag}}-prev"
                    V2rayConfig.Outbounds.add(PrevOutbound)
                    Outbound.ensureSockopt().dialerProxy = PrevOutbound.tag
                    Log.i(AppConfig.TAG, "🔗 Prev chain added for ${{outbound.tag}}")
                }}
            }}
            Val NextNode = SettingsManager.getServerViaRemarks(subItem.NextProfile)
            If (NextNode != null) {{
                convertProfile2Outbound(NextNode)?.let {{ nextOutbound ->
                    UpdateOutboundWithGlobalSettings(nextOutbound)
                    nextOutbound.tag = "${{outbound.tag}}-next"
                    V2rayConfig.Outbounds.add(0, nextOutbound)
                    Val originalTag = outbound.tag
                    Outbound.tag = "${{originalTag}}-orig"
                    NextOutbound.ensureSockopt().dialerProxy = outbound.tag
                    Log.i(AppConfig.TAG, "🔗 Next chain added for ${{outbound.tag}}")
                }}
            }}
        }} catch (e: Exception) {{
            Log.e(AppConfig.TAG, "❌ Chain proxy failed", e)
        }}
    }}
'''
            lines.Insert(i, new_methods)
            content = '\n'.join(lines)
            print("  ✓ Inserted custom outbound methods before GetMoreOutbounds")
            break
    else:
        print("  ✗ Failed to insert custom outbound methods – anchor line not found")
        return False

    # ------------------------------------------------------------------
    # 4. Patch GetRouting – FIXED for new code structure with try-catch
    # ------------------------------------------------------------------
    # The patch needs to insert BEFORE the forEach block but INSIDE the try block
    old_getRouting_start = '''            val rulesetItems = MmkvManager.decodeRoutingRulesets()'''
    
    # Find where GetRoutingUserRule is called inside try block
    old_getRouting_loop = '''            rulesetItems?.forEach {{ key ->
                GetRoutingUserRule(key, v2rayConfig)
            }}'''
    
    new_getRouting = '''            val rulesetItems = MmkvManager.decodeRoutingRulesets()
            val customOutbounds = mutableSetOf<String>()
            // Collect custom outbound tags first
            rulesetItems?.forEach {{ key ->
                If (key.enabled && isCustomOutboundTag(key.outboundTag)) {{
                    customOutbounds.add(key.outboundTag)
                }}
            }}
            Log.i(AppConfig.TAG, "🎯 Custom outbound tags: $customOutbounds")
            // Configure custom outbounds BEFORE adding routing rules that reference them
            customOutbounds.forEach {{ configureCustomOutbound(v2rayConfig, it) }}
            // Now add all routing Rules
            rulesetItems?.forEach {{ key ->
                GetRoutingUserRule(key, v2rayConfig)
            }}'''
    
    # We need to find and replace the entire forEach block inside GetRouting
    # First, let's find the try block and the forEach inside it
    
    # Find the pattern: try { ... val rulesetItems = ... rulesetItems?.forEach ... }
    pattern = r'(try\s*\{{[^}]*val\s+rulesetItems\s*=\s*MmkvManager\.decodeRoutingRulesets\(\)[^}]*rulesetItems\?\.forEach\s*\{{[^}]*GetRoutingUserRule\([^}]*\}}\s*\}})'
    
    replacement = r'''            val rulesetItems = MmkvManager.decodeRoutingRulesets()
            val customOutbounds = mutableSetOf<String>()
            // Collect custom outbound tags first
            rulesetItems?.forEach {{ key ->
                if (key.enabled && isCustomOutboundTag(key.outboundTag)) {{
                    customOutbounds.add(key.outboundTag)
                }}
            }}
            Log.i(AppConfig.TAG, "🎯 Custom outbound tags: $customOutbounds")
            // Configure custom outbounds BEFORE adding routing rules that reference them
            customOutbounds.forEach {{ configureCustomOutbound(v2rayConfig, it) }}
            // Now add all routing Rules
            rulesetItems?.forEach {{ key ->
                GetRoutingUserRule(key, v2rayConfig)
            }}'''
    
    # Actually, simpler approach: replace the entire GetRouting function content
    # Find from "private fun GetRouting" to the closing "    return true\n    }"
    
    GetRouting_pattern = r'(private\s+fun\s+GetRouting\([^)]+\):[^}]+try\s*\{[^}]+?\}\s+catch[^}]+?\}\s+return\s+true\s*\})'
    
    # But that's too complex. Let's use line-by-line replacement instead.
    
    # Read the file and find the specific lines to replace
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Find line with "rulesetItems?.forEach" inside GetRouting
    for i, line in enumerate(lines):
        If 'rulesetItems?.forEach {{ key ->' in line and i > 0:
            # Check if previous line has "try {"
            If 'try {' in lines[i-1]:
                # Found it, now we need to replace from this line to the end of the forEach block
                # Find the closing brace of the forEach
                start_idx = i
                brace_count = 0
                for j in range(i, len(lines)):
                    If '{{' in lines[j]:
                        brace_count += 1
                    If '}}' in lines[j]:
                        brace_count -= 1
                        If brace_count == 0:
                            # Found the end
                            end_idx = j
                            break
                
                # Build new content
                new_content = '''            val rulesetItems = MmkvManager.decodeRoutingRulesets()
            val customOutbounds = mutableSetOf<String>()
            // Collect custom outbound tags first
            rulesetItems?.forEach {{ key ->
                If (key.enabled && isCustomOutboundTag(key.outboundTag)) {{
                    customOutbounds.add(key.outboundTag)
                }}
            }}
            Log.i(AppConfig.TAG, "🎯 Custom outbound tags: $customOutbounds")
            // Configure custom outbounds BEFORE adding routing rules that reference them
            customOutbounds.forEach {{ configureCustomOutbound(v2rayConfig, it) }}
            // Now add all routing Rules
'''
                # Replace lines from start_idx to end_idx
                lines = lines[:start_idx] + [new_content] + lines[end_idx+1:]
                break
    
    with open(filepath, 'w') as f:
        f.writelines(lines)
    
    print("  ✓ V2rayConfigManager.kt")
    return True

def main():
    print("=" * 70)
    print("Custom Outbound Patcher – Fixed Version")
    print("=" * 70)
    results = []
    for name, func in [
        ("RulesetItem.kt", modify_ruleset_item),
        ("arrays.xml", modify_arrays_xml),
        ("activity_routing_edit.xml", modify_layout),
        ("Strings.xml", modify_strings_xml),
        ("RoutingEditActivity.kt", modify_routing_edit_activity),
        ("V2rayConfigManager.kt", modify_v2ray_config_manager),
    ]:
        try:
            ok = func()
            results.append((Name, ok))
        except Exception as e:
            print(f"  ✗ {Name}: {e}")
            results.append((Name, False))
    print("=" * 70)
    success = sum(1 for _, ok in results if ok)
    print(f"\n✅ {success}/{len(results)} Files patched successfully.")
    If success == len(results):
        print("\n👉 Rebuild the app and test a routing rule with 'custom' outbound.")
        print("   - When creating a new rule, the spinner defaults to 'proxy'.")
        print("   - Select 'custom' from the spinner – the custom input field appears.")
        print("   - Type the EXACT remark of an existing server and save.")
        print("\n📱 Check logcat (filter 'v2rayNG') to confirm:")
        print('   adb logcat -s v2rayNG')
        print("   You should see: 🎯 Custom outbound tags: [...] ✅ Custom outbound added at index 0: ...")
    else:
        print("\n❌ Some patches failed – check the error messages above.")

If __name__ == "__main__":
    import re  # only used in layout and strings
    main()

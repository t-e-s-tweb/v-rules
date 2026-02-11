#!/usr/bin/env python3
import os
import shutil
from datetime import datetime

def modify_ruleset_item():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/dto/RulesetItem.kt"
    print(f"\nProcessing {filepath}...")
    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False
    with open(filepath, 'r') as f:
        content = f.read()
    old_line = '    var locked: Boolean? = false,'
    new_lines = '''    var locked: Boolean? = false,
    var customOutboundTag: String? = null,'''
    if old_line not in content:
        print("  ✗ Could not find insertion point")
        return False
    content = content.replace(old_line, new_lines)
    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ Added customOutboundTag field")
    return True

def modify_arrays_xml():
    filepath = "V2rayNG/app/src/main/res/values/arrays.xml"
    print(f"\nProcessing {filepath}...")
    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False
    with open(filepath, 'r') as f:
        content = f.read()
    old_line = '        <item>block</item>'
    new_lines = '''        <item>block</item>
        <item>custom</item>'''
    if old_line not in content:
        print("  ✗ Could not find insertion point")
        return False
    content = content.replace(old_line, new_lines)
    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ Added 'custom' to outbound_tag array")
    return True

def modify_layout():
    filepath = "V2rayNG/app/src/main/res/layout/activity_routing_edit.xml"
    print(f"\nProcessing {filepath}...")
    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False
    with open(filepath, 'r') as f:
        content = f.read()

    old_marker = 'android:entries="@array/outbound_tag" />'
    if old_marker not in content:
        print("  ✗ Could not find spinner")
        return False

    parts = content.split(old_marker)
    if len(parts) != 2:
        print("  ✗ Could not parse layout")
        return False

    after_spinner = parts[1]
    close_idx = after_spinner.find('</LinearLayout>')
    if close_idx == -1:
        print("  ✗ Could not find closing tag")
        return False

    new_layout = '''            </LinearLayout>

            <LinearLayout
                android:id="@+id/layout_custom_outbound"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical"
                android:visibility="gone">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/routing_settings_custom_outbound_tag" />

                <EditText
                    android:id="@+id/et_custom_outbound_tag"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:inputType="text"
                    android:hint="@string/routing_settings_custom_outbound_hint" />
            </LinearLayout>'''

    new_content = parts[0] + old_marker + after_spinner[:close_idx] + new_layout + after_spinner[close_idx:]
    with open(filepath, 'w') as f:
        f.write(new_content)
    print("  ✓ Added custom outbound input layout")
    return True

def modify_routing_edit_activity():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/ui/RoutingEditActivity.kt"
    print(f"\nProcessing {filepath}...")
    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False
    with open(filepath, 'r') as f:
        content = f.read()

    # ---- 1. Add import ----
    content = content.replace(
        'import com.v2ray.ang.extension.nullIfBlank',
        '''import com.v2ray.ang.extension.nullIfBlank
import com.v2ray.ang.extension.isNotNullEmpty'''
    )

    # ---- 2. Add constant CUSTOM_OUTBOUND_INDEX ----
    content = content.replace(
        'private val outbound_tag: Array<out String> by lazy {\n        resources.getStringArray(R.array.outbound_tag)\n    }',
        '''private val outbound_tag: Array<out String> by lazy {
        resources.getStringArray(R.array.outbound_tag)
    }
    // Index of "custom" in the outbound_tag array (proxy=0, direct=1, block=2, custom=3)
    private val CUSTOM_OUTBOUND_INDEX = 3'''
    )

    # ---- 3. Add spinner listener ----
    content = content.replace(
        'clearServer()\n        }\n    }',
        '''clearServer()
        }

        // Setup listener for outbound tag spinner
        binding.spOutboundTag.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                // Show/hide custom outbound input based on selection
                binding.layoutCustomOutbound.visibility = 
                    if (position == CUSTOM_OUTBOUND_INDEX) android.view.View.VISIBLE 
                    else android.view.View.GONE
            }

            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {
            }
        }
    }'''
    )

    # ---- 4. Modify bindingServer ----
    content = content.replace(
        'binding.spOutboundTag.setSelection(outbound)\n\n        return true',
        '''binding.spOutboundTag.setSelection(outbound)

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

    # ---- 5. Modify clearServer ----
    content = content.replace(
        'binding.spOutboundTag.setSelection(0)\n        return true',
        'binding.spOutboundTag.setSelection(0)\n        binding.etCustomOutboundTag.text = null\n        return true'
    )

    # ---- 6. Modify saveServer ----
    content = content.replace(
        'outboundTag = outbound_tag[binding.spOutboundTag.selectedItemPosition]',
        '''// Handle custom outbound tag
            val selectedOutboundPosition = binding.spOutboundTag.selectedItemPosition
            if (selectedOutboundPosition == CUSTOM_OUTBOUND_INDEX) {
                // Custom selected - use the custom outbound tag value
                outboundTag = binding.etCustomOutboundTag.text.toString().trim()
                customOutboundTag = outboundTag
            } else {
                outboundTag = outbound_tag[selectedOutboundPosition]
                customOutboundTag = null
            }'''
    )

    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ Added custom outbound support to RoutingEditActivity")
    return True

def modify_v2ray_config_manager():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt"
    print(f"\nProcessing {filepath}...")
    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False
    with open(filepath, 'r') as f:
        content = f.read()

    # ---- 1. Add check in getUserRule2Domain ----
    content = content.replace(
        'if (key.enabled && key.outboundTag == tag && !key.domain.isNullOrEmpty()) {',
        '''if (key.enabled && key.outboundTag == tag && !key.domain.isNullOrEmpty()) {
                // Skip custom outbounds - they should not be treated as standard tags
                if (isCustomOutboundTag(key.outboundTag)) return@forEach'''
    )

    # ---- 2. Add isCustomOutboundTag method ----
    content = content.replace(
        'return domain\n    }\n\n    /**\n     * Configures custom local DNS settings.',
        '''return domain
    }

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

    /**
     * Configures custom local DNS settings.'''
    )

    # ---- 3. Add configureCustomOutbound method ----
    content = content.replace(
        'updateOutboundFragment(v2rayConfig)\n        return true\n    }\n\n    /**\n     * Configures additional outbound connections',
        '''updateOutboundFragment(v2rayConfig)
        return true
    }

    /**
     * Configures a custom outbound with chain proxy support.
     * This is used when a routing rule specifies a custom outbound tag.
     *
     * @param v2rayConfig The V2ray configuration object to be modified
     * @param customOutboundTag The custom outbound tag (usually a profile/group name)
     * @return true if the custom outbound was configured successfully, false otherwise
     */
    private fun configureCustomOutbound(v2rayConfig: V2rayConfig, customOutboundTag: String): Boolean {
        try {
            // Try to find the profile/group by remarks (name)
            val profile = SettingsManager.getServerViaRemarks(customOutboundTag)
                ?: return false

            // Check if it's a policy group
            if (profile.configType == EConfigType.POLICYGROUP) {
                // Handle policy group with potential chain proxy
                return addGroupOutboundsWithChain(v2rayConfig, profile)
            } else {
                // Single profile - convert to outbound
                val outbound = convertProfile2Outbound(profile) ?: return false
                val ret = updateOutboundWithGlobalSettings(outbound)
                if (!ret) return false

                // Set the custom tag
                outbound.tag = customOutboundTag

                // Add to outbounds if not already present
                if (v2rayConfig.outbounds.none { it.tag == customOutboundTag }) {
                    v2rayConfig.outbounds.add(outbound)
                }

                // Check for chain proxy in subscription
                if (!profile.subscriptionId.isNullOrEmpty()) {
                    setupChainProxyForOutbound(v2rayConfig, outbound, profile.subscriptionId)
                }

                return true
            }
        } catch (e: Exception) {
            Log.e(AppConfig.TAG, "Failed to configure custom outbound: $customOutboundTag", e)
            return false
        }
    }

    /**
     * Configures additional outbound connections'''
    )

    # ---- 4. Add setupChainProxyForOutbound method ----
    content = content.replace(
        'return true\n    }\n\n    /**\n     * Updates outbound settings based on global preferences.',
        '''return true
    }

    /**
     * Sets up chain proxy (prev/next) for a custom outbound.
     *
     * @param v2rayConfig The V2ray configuration object to be modified
     * @param outbound The outbound to setup chain proxy for
     * @param subscriptionId The subscription ID to look up chain settings
     */
    private fun setupChainProxyForOutbound(v2rayConfig: V2rayConfig, outbound: OutboundBean, subscriptionId: String) {
        if (subscriptionId.isEmpty()) return

        try {
            val subItem = MmkvManager.decodeSubscription(subscriptionId) ?: return

            // Previous proxy
            val prevNode = SettingsManager.getServerViaRemarks(subItem.prevProfile)
            if (prevNode != null) {
                val prevOutbound = convertProfile2Outbound(prevNode)
                if (prevOutbound != null) {
                    updateOutboundWithGlobalSettings(prevOutbound)
                    prevOutbound.tag = "${outbound.tag}-prev"
                    v2rayConfig.outbounds.add(prevOutbound)
                    outbound.ensureSockopt().dialerProxy = prevOutbound.tag
                }
            }

            // Next proxy
            val nextNode = SettingsManager.getServerViaRemarks(subItem.nextProfile)
            if (nextNode != null) {
                val nextOutbound = convertProfile2Outbound(nextNode)
                if (nextOutbound != null) {
                    updateOutboundWithGlobalSettings(nextOutbound)
                    nextOutbound.tag = "${outbound.tag}-next"
                    v2rayConfig.outbounds.add(0, nextOutbound)
                    val originalTag = outbound.tag
                    outbound.tag = "${originalTag}-orig"
                    nextOutbound.ensureSockopt().dialerProxy = outbound.tag
                }
            }
        } catch (e: Exception) {
            Log.e(AppConfig.TAG, "Failed to setup chain proxy for outbound: ${outbound.tag}", e)
        }
    }

    /**
     * Updates outbound settings based on global preferences.'''
    )

    # ---- 5. Modify getRouting ----
    content = content.replace(
        'val rulesetItems = MmkvManager.decodeRoutingRulesets()\n            rulesetItems?.forEach { key ->\n                getRoutingUserRule(key, v2rayConfig)',
        '''val rulesetItems = MmkvManager.decodeRoutingRulesets()
            val customOutbounds = mutableSetOf<String>()
            rulesetItems?.forEach { key ->
                // Track custom outbounds for later setup
                if (key.enabled && isCustomOutboundTag(key.outboundTag)) {
                    customOutbounds.add(key.outboundTag)
                }
                getRoutingUserRule(key, v2rayConfig)
            }

            // Configure custom outbounds after processing all rules
            customOutbounds.forEach { customTag ->
                configureCustomOutbound(v2rayConfig, customTag)
            }'''
    )

    with open(filepath, 'w') as f:
        f.write(content)
    print("  ✓ Added custom outbound support to V2rayConfigManager")
    return True

def main():
    print("=" * 70)
    print("Custom Outbound Support - Direct File Modification")
    print("=" * 70)

    results = []
    for func, name in [
        (modify_ruleset_item, "RulesetItem.kt"),
        (modify_arrays_xml, "arrays.xml"),
        (modify_layout, "activity_routing_edit.xml"),
        (modify_routing_edit_activity, "RoutingEditActivity.kt"),
        (modify_v2ray_config_manager, "V2rayConfigManager.kt"),
    ]:
        try:
            success = func()
            results.append((name, success))
        except Exception as e:
            print(f"  ✗ Error modifying {name}: {e}")
            results.append((name, False))

    print("\n" + "=" * 70)
    print("Summary:")
    success_count = sum(1 for _, s in results if s)
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    print("=" * 70)
    print(f"\nSuccessfully modified {success_count}/{len(results)} files")
    if success_count == len(results):
        print("\nAll files modified successfully!")
        print("You can now build the project.")
    else:
        print("\nSome files failed to modify.")
        print("Check the error messages above and manually apply the changes.")
        print("\nBackup files were created with .backup.<timestamp> extension.")

if __name__ == "__main__":
    main()

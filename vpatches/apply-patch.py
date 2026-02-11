#!/usr/bin/env python3
"""
Generate ALL patches for custom outbound support based on actual file contents.
Run this from the root of the v2rayNG repository.
"""

import os
import re
import hashlib

def get_file_hash(content):
    """Generate git-like hash for file content"""
    if not content.endswith('\n'):
        content += '\n'
    header = f"blob {len(content)}\0"
    data = header.encode() + content.encode()
    return hashlib.sha1(data).hexdigest()[:8]

def create_patch_header(old_file, new_file, old_content, new_content):
    """Create git patch header"""
    old_hash = get_file_hash(old_content)
    new_hash = get_file_hash(new_content)
    return f"diff --git a/{old_file} b/{new_file}\nindex {old_hash}..{new_hash} 100644\n--- a/{old_file}\n+++ b/{old_file}"

def find_context(lines, pattern, start=0):
    """Find line index matching pattern"""
    for i in range(start, len(lines)):
        if pattern in lines[i]:
            return i
    return None

def patch_ruleset_item():
    """Patch RulesetItem.kt - Add customOutboundTag field"""
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/dto/RulesetItem.kt"
    print(f"Processing {filepath}...")

    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False

    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')

    # Find line with "var locked: Boolean? = false,"
    target_idx = None
    for i, line in enumerate(lines):
        if 'var locked: Boolean? = false' in line and line.strip().endswith(','):
            target_idx = i
            break

    if target_idx is None:
        print("  ✗ Could not find insertion point")
        return False

    # Insert new field after locked
    new_lines = lines[:target_idx+1] + ['    var customOutboundTag: String? = null,'] + lines[target_idx+1:]
    new_content = '\n'.join(new_lines)

    # Generate patch
    patch_lines = [
        create_patch_header(filepath, filepath, content, new_content),
        f"@@ -{target_idx-1},4 +{target_idx-1},5 @@ data class RulesetItem(",
        lines[target_idx-2],
        lines[target_idx-1],
        lines[target_idx],
        "+    var customOutboundTag: String? = null,",
        lines[target_idx+1] if target_idx+1 < len(lines) else ")"
    ]

    with open('/tmp/ruleset_item.patch', 'w') as f:
        f.write('\n'.join(patch_lines))

    print("  ✓ Created /tmp/ruleset_item.patch")
    return True

def patch_arrays_xml():
    """Patch arrays.xml - Add 'custom' to outbound_tag"""
    filepath = "V2rayNG/app/src/main/res/values/arrays.xml"
    print(f"Processing {filepath}...")

    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False

    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')

    # Find <item>block</item>
    target_idx = None
    for i, line in enumerate(lines):
        if '<item>block</item>' in line:
            target_idx = i
            break

    if target_idx is None:
        print("  ✗ Could not find insertion point")
        return False

    # Get indentation
    indent = '        '
    for i in range(target_idx, -1, -1):
        if lines[i].strip().startswith('<item>'):
            indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            break

    # Insert new item
    new_lines = lines[:target_idx+1] + [f'{indent}<item>custom</item>'] + lines[target_idx+1:]
    new_content = '\n'.join(new_lines)

    # Generate patch
    patch_lines = [
        create_patch_header(filepath, filepath, content, new_content),
        f"@@ -{target_idx-1},6 +{target_idx-1},7 @@",
        lines[target_idx-2],
        lines[target_idx-1],
        lines[target_idx],
        f"+{indent}<item>custom</item>",
        lines[target_idx+1] if target_idx+1 < len(lines) else "",
        lines[target_idx+2] if target_idx+2 < len(lines) else ""
    ]

    with open('/tmp/arrays.patch', 'w') as f:
        f.write('\n'.join(patch_lines))

    print("  ✓ Created /tmp/arrays.patch")
    return True

def patch_layout():
    """Patch activity_routing_edit.xml - Add custom outbound layout"""
    filepath = "V2rayNG/app/src/main/res/layout/activity_routing_edit.xml"
    print(f"Processing {filepath}...")

    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False

    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')

    # Find the spinner layout closing tag
    target_idx = None
    for i, line in enumerate(lines):
        if 'spOutboundTag' in line or (i > 0 and 'android:layout_height="wrap_content" />' in line and i < len(lines) - 1):
            # Look for closing </LinearLayout>
            for j in range(i+1, min(i+5, len(lines))):
                if '</LinearLayout>' in lines[j]:
                    target_idx = j
                    break
            if target_idx:
                break

    if target_idx is None:
        print("  ✗ Could not find insertion point")
        return False

    # New layout to insert
    new_layout = [
        '            <LinearLayout',
        '                android:id="@+id/layout_custom_outbound"',
        '                android:layout_width="match_parent"',
        '                android:layout_height="wrap_content"',
        '                android:layout_marginTop="@dimen/padding_spacing_dp16"',
        '                android:orientation="vertical"',
        '                android:visibility="gone">',
        '',
        '                <TextView',
        '                    android:layout_width="wrap_content"',
        '                    android:layout_height="wrap_content"',
        '                    android:text="@string/routing_settings_custom_outbound_tag" />',
        '',
        '                <EditText',
        '                    android:id="@+id/et_custom_outbound_tag"',
        '                    android:layout_width="match_parent"',
        '                    android:layout_height="wrap_content"',
        '                    android:inputType="text"',
        '                    android:hint="@string/routing_settings_custom_outbound_hint" />',
        '            </LinearLayout>'
    ]

    new_lines = lines[:target_idx+1] + new_layout + lines[target_idx+1:]
    new_content = '\n'.join(new_lines)

    # Generate patch with context
    context_before = lines[target_idx-2:target_idx+1]
    context_after = lines[target_idx+1:target_idx+3] if target_idx+1 < len(lines) else []

    patch_lines = [
        create_patch_header(filepath, filepath, content, new_content),
        f"@@ -{target_idx-1},6 +{target_idx-1},26 @@"
    ]
    patch_lines.extend(context_before)
    patch_lines.append("")
    for line in new_layout:
        patch_lines.append("+" + line)
    patch_lines.extend(context_after)

    with open('/tmp/layout.patch', 'w') as f:
        f.write('\n'.join(patch_lines))

    print("  ✓ Created /tmp/layout.patch")
    return True

def patch_routing_edit_activity():
    """Patch RoutingEditActivity.kt - Add custom outbound support"""
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/ui/RoutingEditActivity.kt"
    print(f"Processing {filepath}...")

    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False

    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')

    # Find all insertion points
    changes = []

    # 1. Add import after nullIfBlank
    for i, line in enumerate(lines):
        if 'import com.v2ray.ang.extension.nullIfBlank' in line:
            changes.append((i+1, '+import com.v2ray.ang.extension.isNotNullEmpty', 'after'))
            break

    # 2. Add CUSTOM_OUTBOUND_INDEX after outbound_tag declaration
    for i, line in enumerate(lines):
        if 'private val outbound_tag' in line and 'by lazy' in line:
            # Find closing brace of lazy block
            for j in range(i, min(i+5, len(lines))):
                if lines[j].strip() == '}':
                    changes.append((j+1, '+    // Index of "custom" in the outbound_tag array (proxy=0, direct=1, block=2, custom=3)', 'after'))
                    changes.append((j+2, '+    private val CUSTOM_OUTBOUND_INDEX = 3', 'after'))
                    break
            break

    # 3. Add spinner listener in onCreate after clearServer()
    for i, line in enumerate(lines):
        if 'clearServer()' in line and 'else' in lines[i-1] if i > 0 else False:
            # Find the closing brace of onCreate setup
            for j in range(i, min(i+10, len(lines))):
                if lines[j].strip() == '}':
                    # Insert after this brace
                    listener_code = [
                        '+',
                        '+        // Setup listener for outbound tag spinner',
                        '+        binding.spOutboundTag.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {',
                        '+            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {',
                        '+                // Show/hide custom outbound input based on selection',
                        '+                binding.layoutCustomOutbound.visibility = ',
                        '+                    if (position == CUSTOM_OUTBOUND_INDEX) android.view.View.VISIBLE ',
                        '+                    else android.view.View.GONE',
                        '+            }',
                        '+',
                        '+            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {',
                        '+            }',
                        '+        }'
                    ]
                    for k, code_line in enumerate(listener_code):
                        changes.append((j+1+k, code_line, 'after'))
                    break
            break

    # 4. Add custom outbound handling in bindingServer
    for i, line in enumerate(lines):
        if 'binding.spOutboundTag.setSelection' in line:
            # Find return true after this
            for j in range(i, min(i+5, len(lines))):
                if 'return true' in lines[j]:
                    custom_code = [
                        '+',
                        '+        // Set custom outbound tag if present',
                        '+        if (rulesetItem.customOutboundTag.isNotNullEmpty()) {',
                        '+            binding.etCustomOutboundTag.text = Utils.getEditable(rulesetItem.customOutboundTag)',
                        '+            // If outboundTag is not in standard list, it might be a custom value',
                        '+            if (outbound == -1 && rulesetItem.outboundTag.isNotNullEmpty()) {',
                        '+                binding.etCustomOutboundTag.text = Utils.getEditable(rulesetItem.outboundTag)',
                        '+            }',
                        '+        }'
                    ]
                    for k, code_line in enumerate(custom_code):
                        changes.append((j+k, code_line, 'before'))
                    break
            break

    # 5. Add clear in clearServer
    for i, line in enumerate(lines):
        if 'binding.chkLocked.isChecked = false' in line:
            changes.append((i+1, '+        binding.etCustomOutboundTag.text = null', 'after'))
            break

    # 6. Replace outbound tag assignment in saveServer
    for i, line in enumerate(lines):
        if 'rulesetItem.outboundTag = outbound_tag' in line and 'selectedItemPosition' in line:
            old_line_idx = i
            # Find the end of this statement
            for j in range(i, min(i+3, len(lines))):
                if lines[j].strip().endswith(')'):
                    # Replace this line and add logic
                    changes.append((old_line_idx, '-        rulesetItem.outboundTag = outbound_tag[binding.spOutboundTag.selectedItemPosition]', 'replace'))
                    new_code = [
                        '+',
                        '+        // Handle custom outbound tag',
                        '+        val selectedOutboundPosition = binding.spOutboundTag.selectedItemPosition',
                        '+        if (selectedOutboundPosition == CUSTOM_OUTBOUND_INDEX) {',
                        '+            // Custom selected - use the custom outbound tag value',
                        '+            rulesetItem.outboundTag = binding.etCustomOutboundTag.text.toString().trim()',
                        '+            rulesetItem.customOutboundTag = rulesetItem.outboundTag',
                        '+        } else {',
                        '+            rulesetItem.outboundTag = outbound_tag[selectedOutboundPosition]',
                        '+            rulesetItem.customOutboundTag = null',
                        '+        }'
                    ]
                    for k, code_line in enumerate(new_code):
                        changes.append((old_line_idx+k+1, code_line, 'after'))
                    break
            break

    if not changes:
        print("  ✗ No changes found to make")
        return False

    # Apply changes in reverse order to maintain indices
    changes.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]

    for idx, code, action in changes:
        if action == 'after':
            new_lines.insert(idx, code[1:] if code.startswith('+') else code)
        elif action == 'before':
            new_lines.insert(idx, code[1:] if code.startswith('+') else code)
        elif action == 'replace':
            if code.startswith('-'):
                # Remove the line
                if idx < len(new_lines) and new_lines[idx] == code[1:]:
                    new_lines.pop(idx)
                else:
                    # Find and remove
                    for i in range(max(0, idx-2), min(len(new_lines), idx+3)):
                        if code[1:] in new_lines[i]:
                            new_lines.pop(i)
                            break

    new_content = '\n'.join(new_lines)

    # Generate unified diff
    import difflib
    diff = difflib.unified_diff(lines, new_lines, lineterm='', 
                                fromfile=f'a/{filepath}', tofile=f'b/{filepath}')
    patch_content = '\n'.join(diff)

    with open('/tmp/routing_edit.patch', 'w') as f:
        f.write(patch_content)

    print("  ✓ Created /tmp/routing_edit.patch")
    return True

def patch_v2ray_config_manager():
    """Patch V2rayConfigManager.kt - Add custom outbound support"""
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt"
    print(f"Processing {filepath}...")

    if not os.path.exists(filepath):
        print(f"  ✗ File not found")
        return False

    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = lines[:]

    # 1. Add isCustomOutboundTag check in getUserRule2Domain
    for i, line in enumerate(lines):
        if 'key.enabled && key.outboundTag == tag' in line:
            # Find the line after this if statement
            for j in range(i, min(i+3, len(lines))):
                if lines[j].strip() == '{':
                    # Insert after opening brace
                    new_lines.insert(j+1, '                // Skip custom outbounds - they should not be treated as standard tags')
                    new_lines.insert(j+2, '                if (isCustomOutboundTag(key.outboundTag)) return@forEach')
                    new_lines.insert(j+3, '')
                    break
            break

    # 2. Add isCustomOutboundTag method after getUserRule2Domain
    for i, line in enumerate(new_lines):
        if 'return domain' in line and i > 0:
            # Check if this is the end of getUserRule2Domain
            indent = len(new_lines[i]) - len(new_lines[i].lstrip())
            if indent == 8:  # Inside function
                # Find the closing brace of the function
                for j in range(i+1, min(i+10, len(new_lines))):
                    if new_lines[j].strip() == '}':
                        # Insert after this
                        method_code = [
                            '',
                            '    /**',
                            '     * Checks if an outbound tag is a custom (user-defined) outbound.',
                            '     * Custom outbounds are those that don\'t match the standard tags (proxy, direct, block).',
                            '     *',
                            '     * @param tag The outbound tag to check',
                            '     * @return true if the tag is custom, false otherwise',
                            '     */',
                            '    private fun isCustomOutboundTag(tag: String): Boolean {',
                            '        return tag != AppConfig.TAG_PROXY && tag != AppConfig.TAG_DIRECT && tag != AppConfig.TAG_BLOCKED',
                            '    }'
                        ]
                        for k, code_line in enumerate(method_code):
                            new_lines.insert(j+1+k, code_line)
                        break
                break

    # 3. Add configureCustomOutbound method after getOutbounds
    # Find the end of getOutbounds method
    for i, line in enumerate(new_lines):
        if 'private fun getOutbounds(' in line:
            # Find return true at end
            for j in range(i, min(i+100, len(new_lines))):
                if new_lines[j].strip() == 'return true' and j > i:
                    # Find closing brace
                    for k in range(j+1, min(j+5, len(new_lines))):
                        if new_lines[k].strip() == '}':
                            # Insert after this method
                            method_code = [
                                '',
                                '    /**',
                                '     * Configures a custom outbound with chain proxy support.',
                                '     * This is used when a routing rule specifies a custom outbound tag.',
                                '     *',
                                '     * @param v2rayConfig The V2ray configuration object to be modified',
                                '     * @param customOutboundTag The custom outbound tag (usually a profile/group name)',
                                '     * @return true if the custom outbound was configured successfully, false otherwise',
                                '     */',
                                '    private fun configureCustomOutbound(v2rayConfig: V2rayConfig, customOutboundTag: String): Boolean {',
                                '        try {',
                                '            // Try to find the profile/group by remarks (name)',
                                '            val profile = SettingsManager.getServerViaRemarks(customOutboundTag)',
                                '                ?: return false',
                                '',
                                '            // Check if it\'s a policy group',
                                '            if (profile.configType == EConfigType.POLICYGROUP) {',
                                '                // Handle policy group with potential chain proxy',
                                '                return addGroupOutboundsWithChain(v2rayConfig, profile)',
                                '            } else {',
                                '                // Single profile - convert to outbound',
                                '                val outbound = convertProfile2Outbound(profile) ?: return false',
                                '                val ret = updateOutboundWithGlobalSettings(outbound)',
                                '                if (!ret) return false',
                                '',
                                '                // Set the custom tag',
                                '                outbound.tag = customOutboundTag',
                                '',
                                '                // Add to outbounds if not already present',
                                '                if (v2rayConfig.outbounds.none { it.tag == customOutboundTag }) {',
                                '                    v2rayConfig.outbounds.add(outbound)',
                                '                }',
                                '',
                                '                // Check for chain proxy in subscription',
                                '                if (!profile.subscriptionId.isNullOrEmpty()) {',
                                '                    setupChainProxyForOutbound(v2rayConfig, outbound, profile.subscriptionId)',
                                '                }',
                                '',
                                '                return true',
                                '            }',
                                '        } catch (e: Exception) {',
                                '            Log.e(AppConfig.TAG, "Failed to configure custom outbound: $customOutboundTag", e)',
                                '            return false',
                                '        }',
                                '    }'
                            ]
                            for m, code_line in enumerate(method_code):
                                new_lines.insert(k+1+m, code_line)
                            break
                    break
            break

    # 4. Add setupChainProxyForOutbound method after updateOutboundWithGlobalSettings
    for i, line in enumerate(new_lines):
        if 'private fun updateOutboundWithGlobalSettings(' in line:
            # Find return true at end
            for j in range(i, min(i+200, len(new_lines))):
                if new_lines[j].strip() == 'return true' and j > i:
                    # Find closing brace
                    for k in range(j+1, min(j+5, len(new_lines))):
                        if new_lines[k].strip() == '}':
                            method_code = [
                                '',
                                '    /**',
                                '     * Sets up chain proxy (prev/next) for a custom outbound.',
                                '     *',
                                '     * @param v2rayConfig The V2ray configuration object to be modified',
                                '     * @param outbound The outbound to setup chain proxy for',
                                '     * @param subscriptionId The subscription ID to look up chain settings',
                                '     */',
                                '    private fun setupChainProxyForOutbound(v2rayConfig: V2rayConfig, outbound: OutboundBean, subscriptionId: String) {',
                                '        if (subscriptionId.isEmpty()) return',
                                '',
                                '        try {',
                                '            val subItem = MmkvManager.decodeSubscription(subscriptionId) ?: return',
                                '',
                                '            // Previous proxy',
                                '            val prevNode = SettingsManager.getServerViaRemarks(subItem.prevProfile)',
                                '            if (prevNode != null) {',
                                '                val prevOutbound = convertProfile2Outbound(prevNode)',
                                '                if (prevOutbound != null) {',
                                '                    updateOutboundWithGlobalSettings(prevOutbound)',
                                '                    prevOutbound.tag = "${outbound.tag}-prev"',
                                '                    v2rayConfig.outbounds.add(prevOutbound)',
                                '                    outbound.ensureSockopt().dialerProxy = prevOutbound.tag',
                                '                }',
                                '            }',
                                '',
                                '            // Next proxy',
                                '            val nextNode = SettingsManager.getServerViaRemarks(subItem.nextProfile)',
                                '            if (nextNode != null) {',
                                '                val nextOutbound = convertProfile2Outbound(nextNode)',
                                '                if (nextOutbound != null) {',
                                '                    updateOutboundWithGlobalSettings(nextOutbound)',
                                '                    nextOutbound.tag = "${outbound.tag}-next"',
                                '                    v2rayConfig.outbounds.add(0, nextOutbound)',
                                '                    val originalTag = outbound.tag',
                                '                    outbound.tag = "${originalTag}-orig"',
                                '                    nextOutbound.ensureSockopt().dialerProxy = outbound.tag',
                                '                }',
                                '            }',
                                '        } catch (e: Exception) {',
                                '            Log.e(AppConfig.TAG, "Failed to setup chain proxy for outbound: ${outbound.tag}", e)',
                                '        }',
                                '    }'
                            ]
                            for m, code_line in enumerate(method_code):
                                new_lines.insert(k+1+m, code_line)
                            break
                    break
            break

    # 5. Modify getRouting method
    # This is complex - we need to replace the entire method body
    # For now, we'll add the custom outbound tracking at the beginning
    for i, line in enumerate(new_lines):
        if 'private fun getRouting(v2rayConfig: V2rayConfig)' in line:
            # Find opening brace
            for j in range(i, min(i+5, len(new_lines))):
                if new_lines[j].strip() == '{':
                    # Insert after opening brace
                    new_lines.insert(j+1, '        try {')
                    new_lines.insert(j+2, '            val rulesetItems = MmkvManager.decodeRoutingRulesets()')
                    new_lines.insert(j+3, '            val customOutbounds = mutableSetOf<String>()')
                    new_lines.insert(j+4, '')
                    break
            break

    new_content = '\n'.join(new_lines)

    # Generate unified diff
    import difflib
    diff = difflib.unified_diff(lines, new_lines, lineterm='',
                                fromfile=f'a/{filepath}', tofile=f'b/{filepath}')
    patch_content = '\n'.join(diff)

    with open('/tmp/config_manager.patch', 'w') as f:
        f.write(patch_content)

    print("  ✓ Created /tmp/config_manager.patch")
    return True

def main():
    print("Generating ALL patches for custom outbound support...")
    print("=" * 60)
    print()

    results = []

    try:
        results.append(("RulesetItem.kt", patch_ruleset_item()))
    except Exception as e:
        print(f"  ✗ Error: {e}")
        results.append(("RulesetItem.kt", False))

    print()

    try:
        results.append(("arrays.xml", patch_arrays_xml()))
    except Exception as e:
        print(f"  ✗ Error: {e}")
        results.append(("arrays.xml", False))

    print()

    try:
        results.append(("activity_routing_edit.xml", patch_layout()))
    except Exception as e:
        print(f"  ✗ Error: {e}")
        results.append(("activity_routing_edit.xml", False))

    print()

    try:
        results.append(("RoutingEditActivity.kt", patch_routing_edit_activity()))
    except Exception as e:
        print(f"  ✗ Error: {e}")
        results.append(("RoutingEditActivity.kt", False))

    print()

    try:
        results.append(("V2rayConfigManager.kt", patch_v2ray_config_manager()))
    except Exception as e:
        print(f"  ✗ Error: {e}")
        results.append(("V2rayConfigManager.kt", False))

    print()
    print("=" * 60)
    print("Summary:")
    success_count = sum(1 for _, success in results if success)
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    print()
    print(f"Successfully generated {success_count}/{len(results)} patches")
    print()
    print("To apply patches, run:")
    print("  git apply /tmp/ruleset_item.patch")
    print("  git apply /tmp/arrays.patch")
    print("  git apply /tmp/layout.patch")
    print("  git apply /tmp/routing_edit.patch")
    print("  git apply /tmp/config_manager.patch")
    print()
    print("Or apply all at once:")
    print("  git apply /tmp/*.patch")

if __name__ == "__main__":
    main()

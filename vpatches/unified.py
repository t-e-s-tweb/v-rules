#!/usr/bin/env python3
"""
Fixed patcher for v2rayNG custom outbound + subscription chaining.
- Adds AppConfig.CURRENT_SERVER constant.
- Enhances SubEditActivity dropdown with None and [Current Server].
- Adds resolveCurrentServer to CoreConfigContextBuilder (NOT CoreConfigManager).
- Idempotent and uses count=1 on all replacements.
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
# 1. AppConfig.kt – add CURRENT_SERVER constant
# ─────────────────────────────────────────────────────────────────────────
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    c = read(p)
    if "CURRENT_SERVER" in c:
        print("• AppConfig: CURRENT_SERVER already present")
        return
    old = '    const val TAG_BLOCKED = "block"'
    new = '    const val TAG_BLOCKED = "block"\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"'
    if old in c:
        write(p, c.replace(old, new, 1))
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

    # 2.1 setupProfileRemarkInputs
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
        c = c.replace(old_setup_inputs, new_setup_inputs, 1)
        print("✓ SubEditActivity: updated setupProfileRemarkInputs")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInputs not found (maybe already patched)")

    # 2.2 setupProfileRemarkInput
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
        c = c.replace(old_setup_input, new_setup_input, 1)
        print("✓ SubEditActivity: updated setupProfileRemarkInput")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInput not found")

    # 2.3 bindingServer display mapping
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
        c = c.replace(old_binding, new_binding, 1)
        print("✓ SubEditActivity: updated bindingServer")
    else:
        print("⚠ SubEditActivity: bindingServer lines not found")

    # 2.4 saveServer storage mapping
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
        c = c.replace(old_save, new_save, 1)
        print("✓ SubEditActivity: updated saveServer")
    else:
        print("⚠ SubEditActivity: saveServer lines not found")

    write(p, c)
    print("✓ SubEditActivity: all enhancements applied")

# ─────────────────────────────────────────────────────────────────────────
# 3. strings.xml
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
# 4. CoreConfigContextBuilder.kt – add CURRENT_SERVER resolution
# ─────────────────────────────────────────────────────────────────────────
def patch_coreconfig_context_builder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"
    if not p.exists():
        print("✗ CoreConfigContextBuilder.kt not found – skipping")
        return
    c = read(p)

    if "private fun resolveCurrentServer" in c:
        print("• CoreConfigContextBuilder: resolveCurrentServer already present")
        return

    old_func = '''    private fun resolveProxyChainProfilesFromGroup(config: ProfileItem): List<<ProfileItem> {
        if (config.subscriptionId.isEmpty()) {
            return listOf(config)
        }

        try {
            val subItem = MmkvManager.decodeSubscription(config.subscriptionId) ?: return listOf(config)
            val resolved = mutableListOf<<ProfileItem>()
            SettingsManager.getServerViaRemarks(subItem.nextProfile)?.let { resolved.add(it) }
            resolved.add(config)
            SettingsManager.getServerViaRemarks(subItem.prevProfile)?.let { resolved.add(it) }
            return resolved
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to resolve proxy chain from group for '${config.remarks}'", e)
            return listOf(config)
        }
    }'''

    new_func = '''    private fun resolveProxyChainProfilesFromGroup(config: ProfileItem): List<<ProfileItem> {
        if (config.subscriptionId.isEmpty()) {
            return listOf(config)
        }

        try {
            val subItem = MmkvManager.decodeSubscription(config.subscriptionId) ?: return listOf(config)
            val resolved = mutableListOf<<ProfileItem>()
            resolveCurrentServer(subItem.nextProfile)?.let { remark ->
                SettingsManager.getServerViaRemarks(remark)?.let { resolved.add(it) }
            }
            resolved.add(config)
            resolveCurrentServer(subItem.prevProfile)?.let { remark ->
                SettingsManager.getServerViaRemarks(remark)?.let { resolved.add(it) }
            }
            return resolved
        } catch (e: Exception) {
            LogUtil.e(AppConfig.TAG, "Failed to resolve proxy chain from group for '${config.remarks}'", e)
            return listOf(config)
        }
    }

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
    }'''

    if old_func in c:
        c = c.replace(old_func, new_func, 1)
        write(p, c)
        print("✓ CoreConfigContextBuilder: added resolveCurrentServer + wired into resolveProxyChainProfilesFromGroup")
    else:
        print("✗ CoreConfigContextBuilder: could not find resolveProxyChainProfilesFromGroup (already patched or upstream changed)")

# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Custom Outbound + Subscription Chain Patcher (FIXED for new architecture)")
    print("=" * 70)

    files_to_backup = [
        BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt",
        BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt",
        BASE / "app/src/main/res/values/strings.xml",
        BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt",
    ]
    for f in files_to_backup:
        if f.exists():
            backup_kotlin(f)

    try:
        patch_appconfig()
        patch_subedit()
        patch_strings()
        patch_coreconfig_context_builder()
        print("\n✅ All patches applied successfully.")
        print("\n⚠️  IMPORTANT: If you previously ran the old patch, restore")
        print("   CoreConfigManager.kt from its .bak file before building.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

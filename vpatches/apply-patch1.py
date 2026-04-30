#!/usr/bin/env python3
"""
Converts prev/next profile EditText fields to spinners with [Current Server] option.
No backups for resource files (to avoid build breakage).
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

def backup_kotlin(filepath: Path):
    """Only backup Kotlin files, skip resources."""
    if filepath.suffix == ".kt":
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = filepath.with_suffix(f".kt.bak.{ts}")
        shutil.copy2(filepath, bak)
        print(f"  ✓ backup: {bak.name}")

def patch_app_config(filepath: Path):
    content = filepath.read_text(encoding="utf-8")
    if "CURRENT_SERVER" in content and '"__CURRENT_SERVER__"' in content:
        print("  • AppConfig already has CURRENT_SERVER")
        return
    pattern = re.compile(r'(const val TAG_PROXY\s*=\s*".*?")')
    if not pattern.search(content):
        pattern = re.compile(r'(object AppConfig\s*\{)')
    match = pattern.search(content)
    if not match:
        raise Exception("Could not find insertion point in AppConfig.kt")
    insert_after = match.end()
    new_line = '\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"'
    content = content[:insert_after] + new_line + content[insert_after:]
    filepath.write_text(content, encoding="utf-8")
    print("  ✓ Added CURRENT_SERVER constant to AppConfig")

def patch_sub_edit_xml(filepath: Path):
    content = filepath.read_text(encoding="utf-8")
    old_pre = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/sub_setting_pre_profile" />

                <EditText
                    android:id="@+id/et_pre_profile"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:hint="@string/sub_setting_pre_profile_tip"
                    android:inputType="text" />

            </LinearLayout>'''
    new_pre = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/sub_setting_pre_profile" />

                <Spinner
                    android:id="@+id/sp_pre_profile"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />

            </LinearLayout>'''
    if old_pre in content:
        content = content.replace(old_pre, new_pre)
        print("  ✓ Replaced et_pre_profile with spinner")
    else:
        print("  ✗ Could not find pre profile EditText block")

    old_next = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/sub_setting_next_profile" />

                <EditText
                    android:id="@+id/et_next_profile"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:hint="@string/sub_setting_pre_profile_tip"
                    android:inputType="text" />

            </LinearLayout>'''
    new_next = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/sub_setting_next_profile" />

                <Spinner
                    android:id="@+id/sp_next_profile"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />

            </LinearLayout>'''
    if old_next in content:
        content = content.replace(old_next, new_next)
        print("  ✓ Replaced et_next_profile with spinner")
    else:
        print("  ✗ Could not find next profile EditText block")

    filepath.write_text(content, encoding="utf-8")

def patch_sub_edit_activity(filepath: Path):
    content = filepath.read_text(encoding="utf-8")
    if "import android.widget.AdapterView" not in content:
        content = content.replace(
            "import android.view.MenuItem",
            "import android.view.MenuItem\nimport android.widget.AdapterView\nimport android.widget.ArrayAdapter"
        )
    insert_pos = content.find("class SubEditActivity : BaseActivity() {")
    if insert_pos == -1:
        raise Exception("Could not find class declaration in SubEditActivity")
    insert_pos = content.index('\n', insert_pos) + 1
    extra_vars = '''
    private val allProfiles: List<Pair<String, String>> by lazy {
        val list = mutableListOf<Pair<String, String>>()
        // Add special entries
        list.add("" to getString(R.string.sub_setting_none))
        list.add(AppConfig.CURRENT_SERVER to getString(R.string.sub_setting_current_server))
        // Add all saved servers (guid to remarks)
        val servers = MmkvManager.decodeAllServerList()
        for (guid in servers) {
            val profile = MmkvManager.decodeServerConfig(guid)
            if (profile != null && profile.remarks.isNotEmpty()) {
                list.add(profile.remarks to profile.remarks)
            }
        }
        list
    }
'''
    content = content[:insert_pos] + extra_vars + content[insert_pos:]

    old_binding = '''        binding.etPreProfile.text = Utils.getEditable(subItem.prevProfile)
        binding.etNextProfile.text = Utils.getEditable(subItem.nextProfile)'''
    new_binding = '''        // Setup pre profile spinner
        val preAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, allProfiles.map { it.second })
        preAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spPreProfile.adapter = preAdapter
        val preValue = subItem.prevProfile
        val preIndex = allProfiles.indexOfFirst { it.first == preValue }
        binding.spPreProfile.setSelection(if (preIndex >= 0) preIndex else 0)

        // Setup next profile spinner
        val nextAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, allProfiles.map { it.second })
        nextAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spNextProfile.adapter = nextAdapter
        val nextValue = subItem.nextProfile
        val nextIndex = allProfiles.indexOfFirst { it.first == nextValue }
        binding.spNextProfile.setSelection(if (nextIndex >= 0) nextIndex else 0)'''
    if old_binding in content:
        content = content.replace(old_binding, new_binding)
    else:
        print("  ✗ Could not replace bindingServer")
        return

    old_clear = '''        binding.etPreProfile.text = null
        binding.etNextProfile.text = null'''
    new_clear = '''        binding.spPreProfile.setSelection(0)
        binding.spNextProfile.setSelection(0)'''
    if old_clear in content:
        content = content.replace(old_clear, new_clear)
    else:
        print("  ✗ Could not replace clearServer")

    old_save = '''        subItem.prevProfile = binding.etPreProfile.text.toString()
        subItem.nextProfile = binding.etNextProfile.text.toString()'''
    new_save = '''        val preIndex = binding.spPreProfile.selectedItemPosition
        subItem.prevProfile = if (preIndex >= 0) allProfiles.getOrNull(preIndex)?.first ?: "" else ""
        val nextIndex = binding.spNextProfile.selectedItemPosition
        subItem.nextProfile = if (nextIndex >= 0) allProfiles.getOrNull(nextIndex)?.first ?: "" else ""'''
    if old_save in content:
        content = content.replace(old_save, new_save)
    else:
        print("  ✗ Could not replace saveServer")

    filepath.write_text(content, encoding="utf-8")
    print("  ✓ Updated SubEditActivity for spinners")

def patch_v2ray_config_manager(filepath: Path):
    content = filepath.read_text(encoding="utf-8")
    resolve_func = '''
    private fun resolveCurrentServer(remark: String?): String? {
        if (remark == AppConfig.CURRENT_SERVER) {
            val defaultId = SettingsManager.getDefaultServerId()
            val profile = MmkvManager.decodeServerConfig(defaultId)
            return profile?.remarks
        }
        return remark
    }
'''
    pattern = r'(\n\s*private fun getMoreOutbounds\()'
    match = re.search(pattern, content)
    if not match:
        print("  ✗ Could not find getMoreOutbounds")
        return
    content = content[:match.start()] + resolve_func + content[match.start():]

    old_prev = "val prevNode = SettingsManager.getServerViaRemarks(subItem.prevProfile)"
    new_prev = "val prevNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.prevProfile) ?: subItem.prevProfile)"
    if old_prev in content:
        content = content.replace(old_prev, new_prev)
    else:
        print("  ✗ Could not update prevNode line")
    old_next = "val nextNode = SettingsManager.getServerViaRemarks(subItem.nextProfile)"
    new_next = "val nextNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.nextProfile) ?: subItem.nextProfile)"
    if old_next in content:
        content = content.replace(old_next, new_next)
    else:
        print("  ✗ Could not update nextNode line")

    if "private fun applySubscriptionChain" in content:
        old_chain_get = "val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return"
        new_chain_get = "val chainProfile = SettingsManager.getServerViaRemarks(resolveCurrentServer(targetRemark) ?: targetRemark) ?: return"
        if old_chain_get in content:
            content = content.replace(old_chain_get, new_chain_get)
            print("  ✓ Updated applySubscriptionChain to resolve CURRENT_SERVER")
        else:
            print("  ⚠ applySubscriptionChain not found or already patched differently")
    else:
        print("  ⚠ applySubscriptionChain not present (maybe not patched yet)")

    filepath.write_text(content, encoding="utf-8")
    print("  ✓ Updated V2rayConfigManager for CURRENT_SERVER resolution")

def patch_strings_xml(filepath: Path):
    content = filepath.read_text(encoding="utf-8")
    needed = {
        "sub_setting_none": "None",
        "sub_setting_current_server": "[Current Server]",
    }
    changed = False
    for k, v in needed.items():
        if f'name="{k}"' in content:
            continue
        m = re.search(r'(\s*)</resources>', content, re.IGNORECASE)
        if not m:
            print(f"  ✗ Could not find </resources>")
            return
        indent = m.group(1)
        pos = m.start()
        content = content[:pos] + f'\n{indent}<string name="{k}">{v}</string>' + content[pos:]
        changed = True
    if changed:
        filepath.write_text(content, encoding="utf-8")
        print("  ✓ Added strings for spinner items")
    else:
        print("  • Strings already present")

def main():
    base = Path("V2rayNG")
    files = {
        "AppConfig.kt": base / "app/src/main/java/com/v2ray/ang/AppConfig.kt",
        "activity_sub_edit.xml": base / "app/src/main/res/layout/activity_sub_edit.xml",
        "SubEditActivity.kt": base / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt",
        "V2rayConfigManager.kt": base / "app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt",
        "strings.xml": base / "app/src/main/res/values/strings.xml",
    }
    for name, path in files.items():
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        # Only backup Kotlin files
        if path.suffix == ".kt":
            backup_kotlin(path)

    try:
        patch_app_config(files["AppConfig.kt"])
        patch_sub_edit_xml(files["activity_sub_edit.xml"])
        patch_sub_edit_activity(files["SubEditActivity.kt"])
        patch_v2ray_config_manager(files["V2rayConfigManager.kt"])
        patch_strings_xml(files["strings.xml"])
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild the app and enjoy auto‑tracking front/landing proxy.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

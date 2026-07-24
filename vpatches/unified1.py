#!/usr/bin/env python3
"""
v2rayNG Dropdown Slowness Fix (with cache pre‑warm)

- Caches getProfileRemarks() results per excludeConfigTypes set
- Invalidates all caches on server list changes
- Pre‑warms the cache on app startup
"""

import os
import re
import sys

# File paths relative to project root
SETTINGS_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/SettingsManager.kt"
MMKV_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/MmkvManager.kt"
MAIN_ACTIVITY_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/ui/main/MainActivity.kt"

# ----------------------------------------------------------------------
# Patches for SettingsManager.kt

CACHE_FIELDS = """
    // Cached remarks lists by excludeConfigTypes (for fast dropdowns)
    private val cachedProfileRemarksMap = mutableMapOf<Set<EConfigType>, List<String>>()

    /**
     * Invalidates all cached profile remarks lists.
     * Must be called whenever the server list changes.
     */
    fun invalidateProfileRemarksCache() {
        cachedProfileRemarksMap.clear()
    }
"""

NEW_GET_PROFILE_REMARKS_BODY = """
    fun getProfileRemarks(excludeConfigTypes: Set<EConfigType> = setOf(EConfigType.CUSTOM)): List<String> {
        cachedProfileRemarksMap[excludeConfigTypes]?.let { return it }

        val result = decodeAllServerList()
            .asSequence()
            .mapNotNull { guid -> decodeServerConfig(guid) }
            .filter { profile -> profile.configType !in excludeConfigTypes }
            .map { it.remarks.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
            .toList()

        cachedProfileRemarksMap[excludeConfigTypes] = result
        return result
    }
"""

INVALIDATION_LINE = "        SettingsManager.invalidateProfileRemarksCache()\n"

# ----------------------------------------------------------------------
# Patches for MainActivity.kt

PREWARM_CODE = """        // Pre-warm profile remarks cache for fast dropdowns
        lifecycleScope.launch(Dispatchers.IO) {
            SettingsManager.getProfileRemarks()
            SettingsManager.getProfileRemarks(setOf(EConfigType.CUSTOM, EConfigType.POLICYGROUP, EConfigType.PROXYCHAIN))
        }
"""

# ----------------------------------------------------------------------
# Utilities


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def find_matching_brace(text, start_pos):
    depth = 0
    for i in range(start_pos, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


# ----------------------------------------------------------------------
# Patchers


def patch_settings_manager(content):
    # Insert cache fields after "object SettingsManager {"
    obj_pattern = r"(object SettingsManager\s*\{)"
    obj_match = re.search(obj_pattern, content)
    if not obj_match:
        print("[ERROR] Could not find 'object SettingsManager {'")
        return content

    brace_pos = obj_match.end()
    if "cachedProfileRemarksMap" not in content:
        content = content[:brace_pos] + "\n" + CACHE_FIELDS + content[brace_pos:]
        print("[INFO] Added cache fields to SettingsManager")
    else:
        print("[INFO] Cache fields already present")

    # Replace getProfileRemarks
    func_start = content.find("fun getProfileRemarks")
    if func_start == -1:
        print("[ERROR] Could not find 'fun getProfileRemarks'")
        return content

    brace_pos_func = content.find("{", func_start)
    if brace_pos_func == -1:
        print("[ERROR] Could not find opening brace for getProfileRemarks")
        return content

    end_func = find_matching_brace(content, brace_pos_func)
    if end_func == -1:
        print("[ERROR] Could not find closing brace for getProfileRemarks")
        return content

    content = content[:func_start] + NEW_GET_PROFILE_REMARKS_BODY + content[end_func+1:]
    print("[INFO] Replaced getProfileRemarks with cached version")

    return content


def patch_mmkv_manager(content):
    functions = [
        "encodeServerList",
        "removeServer",
        "removeServerViaSubid",
        "removeServers",
        "removeAllServer",
    ]

    for func_name in functions:
        pattern = r"fun\s+" + re.escape(func_name) + r"\s*\("
        match = re.search(pattern, content)
        if not match:
            print(f"[WARNING] Could not find function {func_name}")
            continue

        start_search = match.end()
        brace_pos = content.find("{", start_search)
        if brace_pos == -1:
            print(f"[WARNING] Could not find opening brace for {func_name}")
            continue

        end_func = find_matching_brace(content, brace_pos)
        if end_func == -1:
            print(f"[WARNING] Could not find closing brace for {func_name}")
            continue

        body = content[brace_pos+1:end_func]
        if "SettingsManager.invalidateProfileRemarksCache()" in body:
            print(f"[INFO] Invalidation already present in {func_name}")
            continue

        insert_pos = brace_pos + 1
        if content[insert_pos:insert_pos+1] == "\n":
            insert_pos += 1
        content = content[:insert_pos] + INVALIDATION_LINE + content[insert_pos:]
        print(f"[INFO] Added invalidation to {func_name}")

    return content


def patch_main_activity(content):
    # Look for the line where we initialize the ViewModel and insert after it.
    # Pattern: "mainViewModel.onAction(MainAction.Initialize)"
    pattern = r"(mainViewModel\.onAction\(MainAction\.Initialize\))"
    match = re.search(pattern, content)
    if not match:
        print("[ERROR] Could not find mainViewModel.onAction(MainAction.Initialize) in MainActivity.kt")
        return content

    # Check if pre-warm code is already present.
    if "Pre-warm profile remarks cache" in content:
        print("[INFO] Pre-warm code already present in MainActivity.kt")
        return content

    # Insert after the matched line.
    insert_pos = match.end()
    # Add a newline before the insertion to keep formatting.
    content = content[:insert_pos] + "\n" + PREWARM_CODE + content[insert_pos:]
    print("[INFO] Added cache pre-warm to MainActivity.kt")

    return content


# ----------------------------------------------------------------------
# Main


def main(project_root):
    settings_path = os.path.join(project_root, SETTINGS_FILE)
    mmkv_path = os.path.join(project_root, MMKV_FILE)
    main_path = os.path.join(project_root, MAIN_ACTIVITY_FILE)

    for path in [settings_path, mmkv_path, main_path]:
        if not os.path.isfile(path):
            print(f"[ERROR] File not found: {path}")
            sys.exit(1)

    print("[INFO] Patching SettingsManager.kt...")
    settings_content = read_file(settings_path)
    settings_patched = patch_settings_manager(settings_content)
    if settings_content != settings_patched:
        write_file(settings_path, settings_patched)
        print("[INFO] SettingsManager.kt updated.")
    else:
        print("[INFO] No changes to SettingsManager.kt.")

    print("[INFO] Patching MmkvManager.kt...")
    mmkv_content = read_file(mmkv_path)
    mmkv_patched = patch_mmkv_manager(mmkv_content)
    if mmkv_content != mmkv_patched:
        write_file(mmkv_path, mmkv_patched)
        print("[INFO] MmkvManager.kt updated.")
    else:
        print("[INFO] No changes to MmkvManager.kt.")

    print("[INFO] Patching MainActivity.kt...")
    main_content = read_file(main_path)
    main_patched = patch_main_activity(main_content)
    if main_content != main_patched:
        write_file(main_path, main_patched)
        print("[INFO] MainActivity.kt updated.")
    else:
        print("[INFO] No changes to MainActivity.kt.")

    print("[DONE] All patches applied.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fix_dropdown_slowness.py <project_root>")
        print("  <project_root> - path to the root of the v2rayNG project (containing V2rayNG/ subfolder)")
        sys.exit(1)
    main(sys.argv[1])

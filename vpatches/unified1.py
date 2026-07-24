#!/usr/bin/env python3
"""
v2rayNG Dropdown Slowness Fix v2 (robust)

- Replaces getProfileRemarks() with a cached version
- Invalidates cache on any server list modification
- Pre-warms cache on app startup
- Logs cache hits/misses for debugging
"""

import os
import re
import sys

SETTINGS_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/SettingsManager.kt"
MMKV_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/MmkvManager.kt"
MAIN_ACTIVITY_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/ui/main/MainActivity.kt"

# ----------------------------------------------------------------------
# New SettingsManager code

NEW_SETTINGS_CACHE_FIELDS = """
    // Cached profile remarks with versioning
    private val cachedProfileRemarksMap = java.util.concurrent.ConcurrentHashMap<Set<EConfigType>, Pair<Int, List<String>>>()
    private var cacheVersion = 0

    fun invalidateProfileRemarksCache() {
        cacheVersion++
        cachedProfileRemarksMap.clear()
        LogUtil.d(AppConfig.TAG, "Profile remarks cache invalidated (version $cacheVersion)")
    }
"""

NEW_GET_PROFILE_REMARKS_BODY = """
    fun getProfileRemarks(excludeConfigTypes: Set<EConfigType> = setOf(EConfigType.CUSTOM)): List<String> {
        val currentVersion = cacheVersion
        cachedProfileRemarksMap[excludeConfigTypes]?.let { (version, list) ->
            if (version == currentVersion) {
                LogUtil.d(AppConfig.TAG, "Profile remarks cache HIT for $excludeConfigTypes")
                return list
            }
        }

        LogUtil.d(AppConfig.TAG, "Profile remarks cache MISS for $excludeConfigTypes, rebuilding...")
        val result = decodeAllServerList()
            .asSequence()
            .mapNotNull { guid -> decodeServerConfig(guid) }
            .filter { profile -> profile.configType !in excludeConfigTypes }
            .map { it.remarks.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
            .toList()

        cachedProfileRemarksMap[excludeConfigTypes] = currentVersion to result
        return result
    }
"""

INVALIDATION_LINE = "        SettingsManager.invalidateProfileRemarksCache()\n"

# ----------------------------------------------------------------------
# New MainActivity pre-warm code

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


def find_function_brace(content, func_name):
    """Find the start and end positions of a function by name."""
    pattern = r"fun\s+" + re.escape(func_name) + r"\s*\([^)]*\)\s*[:=]?\s*[^{]*\{"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    brace_pos = match.end() - 1  # position of '{'
    # find matching brace
    depth = 0
    end = -1
    for i in range(brace_pos, len(content)):
        ch = content[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return None
    return start, end


def replace_function(content, func_name, new_body):
    """Replace the entire function definition with new_body."""
    pos = find_function_brace(content, func_name)
    if not pos:
        print(f"[ERROR] Could not find function {func_name}")
        return content
    start, end = pos
    return content[:start] + new_body + content[end+1:]


# ----------------------------------------------------------------------
# Patchers


def patch_settings_manager(content):
    # 1. Insert cache fields after 'object SettingsManager {'
    obj_pattern = r"(object SettingsManager\s*\{)"
    obj_match = re.search(obj_pattern, content)
    if not obj_match:
        print("[ERROR] Could not find 'object SettingsManager {'")
        return content

    brace_pos = obj_match.end()
    if "cachedProfileRemarksMap" not in content:
        content = content[:brace_pos] + "\n" + NEW_SETTINGS_CACHE_FIELDS + content[brace_pos:]
        print("[INFO] Added cache fields")
    else:
        print("[INFO] Cache fields already present")

    # 2. Replace getProfileRemarks
    if "getProfileRemarks" in content:
        content = replace_function(content, "getProfileRemarks", NEW_GET_PROFILE_REMARKS_BODY)
        print("[INFO] Replaced getProfileRemarks")
    else:
        print("[ERROR] Could not find getProfileRemarks")

    return content


def patch_mmkv_manager(content):
    functions = [
        "encodeServerConfig",
        "encodeServerList",
        "removeServer",
        "removeServerViaSubid",
        "removeServers",
        "removeAllServer",
    ]

    for func_name in functions:
        pos = find_function_brace(content, func_name)
        if not pos:
            print(f"[WARNING] Could not find function {func_name}")
            continue

        start, end = pos
        # Check if invalidation already exists
        body = content[start:end+1]
        if "SettingsManager.invalidateProfileRemarksCache()" in body:
            print(f"[INFO] Invalidation already present in {func_name}")
            continue

        # Insert the line after the opening brace
        brace_pos = content.find("{", start)
        if brace_pos == -1:
            continue
        insert_pos = brace_pos + 1
        if content[insert_pos:insert_pos+1] == "\n":
            insert_pos += 1
        content = content[:insert_pos] + INVALIDATION_LINE + content[insert_pos:]
        print(f"[INFO] Added invalidation to {func_name}")

    return content


def patch_main_activity(content):
    pattern = r"(mainViewModel\.onAction\(MainAction\.Initialize\))"
    match = re.search(pattern, content)
    if not match:
        print("[ERROR] Could not find mainViewModel.onAction(MainAction.Initialize)")
        return content

    if "Pre-warm profile remarks cache" in content:
        print("[INFO] Pre-warm already present")
        return content

    insert_pos = match.end()
    content = content[:insert_pos] + "\n" + PREWARM_CODE + content[insert_pos:]
    print("[INFO] Added pre-warm to MainActivity")
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
    print("Please rebuild the app and check the logcat for 'Profile remarks cache' messages.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fix_dropdown_slowness_v2.py <project_root>")
        sys.exit(1)
    main(sys.argv[1])

#!/usr/bin/env python3
"""
v2rayNG Dropdown Slowness Fix Patcher (Improved)
"""

import os
import re
import sys

SETTINGS_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/SettingsManager.kt"
MMKV_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/MmkvManager.kt"

# ----------------------------------------------------------------------
# Patches for SettingsManager.kt

CACHE_FIELDS_AND_INVALIDATE = """
    // Cached remarks list for fast dropdowns
    private var cachedProfileRemarks: List<String>? = null

    /**
     * Invalidates the cached profile remarks list.
     * Must be called whenever the server list changes.
     */
    fun invalidateProfileRemarksCache() {
        cachedProfileRemarks = null
    }
"""

NEW_GET_PROFILE_REMARKS_BODY = """
    fun getProfileRemarks(excludeConfigTypes: Set<EConfigType> = setOf(EConfigType.CUSTOM)): List<String> {
        cachedProfileRemarks?.let { return it }

        val result = decodeAllServerList()
            .asSequence()
            .mapNotNull { guid -> decodeServerConfig(guid) }
            .filter { profile -> profile.configType !in excludeConfigTypes }
            .map { it.remarks.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
            .toList()

        cachedProfileRemarks = result
        return result
    }
"""

# ----------------------------------------------------------------------
# Utility functions


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def find_matching_brace(text, start_pos):
    """Find the position of the closing brace matching the opening brace at start_pos."""
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
# Patcher functions


def patch_settings_manager(content):
    # 1. Insert cache fields after "object SettingsManager {"
    obj_pattern = r"(object SettingsManager\s*\{)"
    obj_match = re.search(obj_pattern, content)
    if not obj_match:
        print("[ERROR] Could not find 'object SettingsManager {' in SettingsManager.kt")
        return content

    # Find the opening brace position and insert after it
    brace_pos = obj_match.end()  # points to the character after '{'
    # Ensure we insert after any whitespace/newline? Actually we want to insert on the next line.
    # We'll insert after the '{' and a newline if not already there.
    # We'll simply insert at brace_pos.
    # But we should check if the cache fields are already present.
    if "cachedProfileRemarks" in content:
        print("[INFO] Cache fields already present in SettingsManager.kt")
    else:
        # Insert after the brace
        content = content[:brace_pos] + "\n" + CACHE_FIELDS_AND_INVALIDATE + content[brace_pos:]

    # 2. Replace the getProfileRemarks function.
    # Find the function by searching for "fun getProfileRemarks".
    # We'll find the start of the function definition.
    func_start = content.find("fun getProfileRemarks")
    if func_start == -1:
        print("[ERROR] Could not find 'fun getProfileRemarks' in SettingsManager.kt")
        return content

    # Find the opening brace of the function.
    # We'll search from func_start for the first '{' that is part of the function.
    # To be safe, we find the line containing the function signature and then find the first '{' after that line.
    # But we can just search forward for the first '{' after func_start, but there might be '{' in the parameter list? No, default args might have braces? Not in Kotlin.
    # Kotlin default values use parentheses and maybe lambdas? But not typical.
    # So we'll find the first '{' after func_start.
    brace_pos_func = content.find("{", func_start)
    if brace_pos_func == -1:
        print("[ERROR] Could not find opening brace for getProfileRemarks")
        return content

    # Find the matching closing brace.
    end_func = find_matching_brace(content, brace_pos_func)
    if end_func == -1:
        print("[ERROR] Could not find closing brace for getProfileRemarks")
        return content

    # Now we need to extract the signature (from func_start to before the opening brace).
    # The signature ends at brace_pos_func.
    # We'll replace everything from func_start to end_func+1 with the new function.
    # But we want to keep any preceding annotations or comments? We'll just replace the whole function.
    # However, we should preserve any whitespace before the function.
    # We'll replace from func_start to end_func+1 with the new function definition.
    new_func = NEW_GET_PROFILE_REMARKS_BODY
    # But ensure we keep the same indentation? The original function is indented with 4 spaces inside the object.
    # The new function body is already indented with 4 spaces.
    # The surrounding code will have the same indentation.
    # We'll just replace the slice.
    content = content[:func_start] + new_func + content[end_func+1:]

    return content


def patch_mmkv_manager(content):
    """Insert invalidation calls in each listed function."""
    invalidation_line = "        SettingsManager.invalidateProfileRemarksCache()\n"
    functions = [
        "encodeServerList",
        "removeServer",
        "removeServerViaSubid",
        "removeServers",
        "removeAllServer",
    ]

    for func_name in functions:
        # Find the function definition. We'll search for "fun functionName(".
        pattern = r"fun\s+" + re.escape(func_name) + r"\s*\("
        match = re.search(pattern, content)
        if not match:
            print(f"[WARNING] Could not find function {func_name} in MmkvManager.kt")
            continue

        # Find the opening brace of the function.
        # Start from the match end.
        start_search = match.end()
        # Find the first '{' after that.
        brace_pos = content.find("{", start_search)
        if brace_pos == -1:
            print(f"[WARNING] Could not find opening brace for {func_name}")
            continue

        # Find the matching closing brace to get the function body.
        end_func = find_matching_brace(content, brace_pos)
        if end_func == -1:
            print(f"[WARNING] Could not find closing brace for {func_name}")
            continue

        # Check if the invalidation line is already in the body.
        body = content[brace_pos+1:end_func]
        if "SettingsManager.invalidateProfileRemarksCache()" in body:
            print(f"[INFO] Invalidation already present in {func_name}, skipping")
            continue

        # Insert the invalidation line right after the opening brace.
        # We'll insert after the brace and a newline if needed.
        insert_pos = brace_pos + 1
        # If there is a newline after the brace, we insert after that newline to keep formatting.
        # We'll check if the next character is newline.
        if content[insert_pos:insert_pos+1] == "\n":
            insert_pos += 1
        # Insert the invalidation line.
        content = content[:insert_pos] + invalidation_line + content[insert_pos:]

    return content


# ----------------------------------------------------------------------
# Main


def main(project_root):
    settings_path = os.path.join(project_root, SETTINGS_FILE)
    mmkv_path = os.path.join(project_root, MMKV_FILE)

    if not os.path.isfile(settings_path):
        print(f"[ERROR] SettingsManager.kt not found at {settings_path}")
        sys.exit(1)
    if not os.path.isfile(mmkv_path):
        print(f"[ERROR] MmkvManager.kt not found at {mmkv_path}")
        sys.exit(1)

    print("[INFO] Reading SettingsManager.kt...")
    settings_content = read_file(settings_path)
    settings_patched = patch_settings_manager(settings_content)
    if settings_content != settings_patched:
        write_file(settings_path, settings_patched)
        print("[INFO] SettingsManager.kt updated.")
    else:
        print("[INFO] No changes needed for SettingsManager.kt.")

    print("[INFO] Reading MmkvManager.kt...")
    mmkv_content = read_file(mmkv_path)
    mmkv_patched = patch_mmkv_manager(mmkv_content)
    if mmkv_content != mmkv_patched:
        write_file(mmkv_path, mmkv_patched)
        print("[INFO] MmkvManager.kt updated.")
    else:
        print("[INFO] No changes needed for MmkvManager.kt.")

    print("[DONE] All patches applied.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fix_dropdown_slowness.py <project_root>")
        print("  <project_root> - path to the root of the v2rayNG project (containing V2rayNG/ subfolder)")
        sys.exit(1)
    main(sys.argv[1])

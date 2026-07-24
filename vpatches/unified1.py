#!/usr/bin/env python3
"""
v2rayNG Dropdown Slowness Fix Patcher

This script:
1. Replaces SettingsManager.getProfileRemarks() with a cached version.
2. Adds cache invalidation calls in all MmkvManager server-list mutating functions.
"""

import os
import re
import sys

# ----------------------------------------------------------------------
# Paths relative to the project root
SETTINGS_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/SettingsManager.kt"
MMKV_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/MmkvManager.kt"

# ----------------------------------------------------------------------
# Patches for SettingsManager.kt

# 1. Add caching fields and invalidate method after the object declaration.
# We'll place them right after the "object SettingsManager {" line.
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

# 2. Replace the old getProfileRemarks with the cached version.
# The old function is:
#    fun getProfileRemarks(...): List<String> { ... }
# We will replace the entire function body with the cached version.
NEW_GET_PROFILE_REMARKS = """
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
# Patches for MmkvManager.kt

# List of functions that modify the server list, and the call to insert.
MMKV_INVALIDATION_FUNCTIONS = [
    "encodeServerList",
    "removeServer",
    "removeServerViaSubid",
    "removeServers",
    "removeAllServer",
]

INVALIDATION_LINE = "        SettingsManager.invalidateProfileRemarksCache()\n"

# ----------------------------------------------------------------------
# Utility functions


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_newline_at_end(content):
    if not content.endswith("\n"):
        content += "\n"
    return content


# ----------------------------------------------------------------------
# Patcher functions


def patch_settings_manager(content):
    """Apply all changes to SettingsManager.kt."""
    # 1. Insert cache fields after "object SettingsManager {"
    # Find the line "object SettingsManager {" and insert the fields after it.
    pattern = r"(object SettingsManager\s*\{)"
    replacement = r"\1\n" + CACHE_FIELDS_AND_INVALIDATE
    content = re.sub(pattern, replacement, content, count=1)

    # 2. Replace the getProfileRemarks function body.
    # We use a regex that matches the entire function, including any preceding modifiers,
    # and captures the signature up to the opening brace, then replaces the body.
    # We'll search for "fun getProfileRemarks(" up to the closing brace of the function.
    # Simpler: match the whole function from "fun getProfileRemarks" to the closing brace
    # that matches the opening brace of the function.
    # We'll use a non-greedy match with balanced braces.
    # A robust way: use a temporary placeholder to avoid nested braces issues,
    # but we know the function is simple and doesn't have inner braces.
    # We'll just replace the function body from the opening brace after signature to the matching closing brace.

    # Find the start of the function signature.
    sig_pattern = r"(fun getProfileRemarks\s*\([^)]*\)\s*:\s*List<String>\s*)\{"
    sig_match = re.search(sig_pattern, content)
    if not sig_match:
        print("[ERROR] Could not find getProfileRemarks signature in SettingsManager.kt")
        return content

    start = sig_match.start(1)  # the entire "fun ..." part
    # Now find the matching closing brace after the opening brace.
    # We'll start from the position of the opening brace (end of the signature).
    brace_pos = content.find("{", sig_match.end())
    if brace_pos == -1:
        print("[ERROR] Could not find opening brace of getProfileRemarks")
        return content

    # Find the matching closing brace.
    depth = 0
    end_pos = -1
    for i in range(brace_pos, len(content)):
        ch = content[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_pos = i
                break

    if end_pos == -1:
        print("[ERROR] Could not find closing brace of getProfileRemarks")
        return content

    # Replace the whole function with the new implementation.
    # We keep the signature (from start to before the brace) and replace the body.
    new_func = content[start:brace_pos] + " {" + NEW_GET_PROFILE_REMARKS + "\n    }"
    content = content[:start] + new_func + content[end_pos+1:]

    return content


def patch_mmkv_manager(content):
    """Insert invalidation calls in each listed function."""
    for func_name in MMKV_INVALIDATION_FUNCTIONS:
        # Find the function definition. We'll insert the invalidation line right after the function's opening brace.
        # Pattern: "fun functionName(...) {" or "fun functionName(...): ReturnType {".
        # We'll match the function name and then the opening brace.
        # Use a regex that finds the function definition and captures the position after the opening brace.
        # We'll be careful to match the exact function name.
        pattern = r"(fun\s+" + re.escape(func_name) + r"\s*\([^)]*\)\s*[:=]?\s*[^{]*?)\{"
        match = re.search(pattern, content)
        if not match:
            print(f"[WARNING] Could not find function {func_name} in MmkvManager.kt")
            continue

        # Insert the invalidation line after the opening brace.
        # We'll find the position of the opening brace and insert the line after it.
        brace_start = match.end()
        # Check if we have already inserted the line (to avoid duplicate invalidation).
        # Look for "SettingsManager.invalidateProfileRemarksCache()" in the function body.
        # We'll search from brace_start to the next closing brace of the function (simplified: we'll search until the next line that starts with "    }" but better to find the matching brace).
        # For simplicity, we'll just check if the line already exists in the first few lines of the function.
        # Find the closing brace of the function.
        depth = 0
        func_end = -1
        for i in range(brace_start, len(content)):
            ch = content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    func_end = i
                    break
        if func_end == -1:
            print(f"[WARNING] Could not find closing brace for {func_name}")
            continue

        # Check if the invalidation line is already present in the function body.
        body = content[brace_start:func_end]
        if "SettingsManager.invalidateProfileRemarksCache()" in body:
            print(f"[INFO] Invalidation already present in {func_name}, skipping")
            continue

        # Insert the invalidation line right after the opening brace.
        # We'll insert at position brace_start+1 (after the '{').
        new_content = content[:brace_start+1] + "\n" + INVALIDATION_LINE + content[brace_start+1:]
        content = new_content

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

#!/usr/bin/env python3
"""
v2rayNG Dropdown Slowness Fix – Working Version

- Caches getProfileRemarks() with versioning
- Invalidates cache on server list changes
- Pre-warms cache on app startup
- Adds search + LazyColumn inside ExposedDropdownMenu (valid ColumnScope)
"""

import os
import re
import sys

SETTINGS_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/SettingsManager.kt"
MMKV_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/MmkvManager.kt"
MAIN_ACTIVITY_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/ui/main/MainActivity.kt"
FORM_FIELDS_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/compose/FormFields.kt"

# ----------------------------------------------------------------------
# Patches for SettingsManager.kt
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
# Patches for MainActivity.kt
PREWARM_CODE = """        // Pre-warm profile remarks cache for fast dropdowns
        lifecycleScope.launch(Dispatchers.IO) {
            SettingsManager.getProfileRemarks()
            SettingsManager.getProfileRemarks(setOf(EConfigType.CUSTOM, EConfigType.POLICYGROUP, EConfigType.PROXYCHAIN))
        }
"""

# ----------------------------------------------------------------------
# Correct ExposedDropdownMenu block with search + LazyColumn
NEW_DROPDOWN_BLOCK = """    ExposedDropdownMenu(
        expanded = expanded,
        onDismissRequest = { expanded = false },
        modifier = Modifier.heightIn(max = 300.dp),
        scrollState = menuScrollState,
        containerColor = MaterialTheme.colorScheme.surface
    ) {
        var searchQuery by rememberSaveable { mutableStateOf("") }
        val filteredOptions = remember(options, searchQuery) {
            if (searchQuery.isEmpty()) options else options.filter { it.contains(searchQuery, ignoreCase = true) }
        }
        Column {
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                placeholder = { Text("Search...") },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                    cursorColor = MaterialTheme.colorScheme.secondary,
                    selectionColors = TextSelectionColors(
                        handleColor = MaterialTheme.colorScheme.secondary,
                        backgroundColor = MaterialTheme.colorScheme.secondary.copy(alpha = 0.4f)
                    )
                )
            )
            Divider()
            LazyColumn(modifier = Modifier.weight(1f)) {
                items(filteredOptions) { option ->
                    DropdownMenuItem(
                        text = { Text(option) },
                        onClick = {
                            onValueChange(option)
                            expanded = false
                            searchQuery = ""
                            focusManager.clearFocus()
                        }
                    )
                }
                if (filteredOptions.isEmpty()) {
                    item {
                        DropdownMenuItem(
                            text = { Text("No results") },
                            onClick = { }
                        )
                    }
                }
            }
        }
    }"""

# Correct imports – note the saveable import
REQUIRED_IMPORTS = [
    "import androidx.compose.foundation.layout.Column",
    "import androidx.compose.foundation.layout.heightIn",
    "import androidx.compose.foundation.layout.weight",
    "import androidx.compose.foundation.lazy.LazyColumn",
    "import androidx.compose.foundation.lazy.items",
    "import androidx.compose.material3.Divider",
    "import androidx.compose.runtime.mutableStateOf",
    "import androidx.compose.runtime.saveable.rememberSaveable",
    "import androidx.compose.runtime.setValue",
    "import androidx.compose.runtime.getValue",
]

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
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def find_function_brace(content, func_name):
    pattern = r"fun\s+" + re.escape(func_name) + r"\s*\([^)]*\)\s*[:=]?\s*[^{]*\{"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    brace_pos = match.end() - 1
    end = find_matching_brace(content, brace_pos)
    if end == -1:
        return None
    return start, end


def replace_function(content, func_name, new_body):
    pos = find_function_brace(content, func_name)
    if not pos:
        print(f"[ERROR] Could not find function {func_name}")
        return content
    start, end = pos
    return content[:start] + new_body + content[end+1:]


# ----------------------------------------------------------------------
# Patchers


def patch_settings_manager(content):
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
        body = content[start:end+1]
        if "SettingsManager.invalidateProfileRemarksCache()" in body:
            print(f"[INFO] Invalidation already present in {func_name}")
            continue

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


def patch_form_fields(content):
    # 1. Add missing imports
    import_block = ""
    for imp in REQUIRED_IMPORTS:
        if imp not in content:
            import_block += imp + "\n"

    if import_block:
        import_pattern = r"(import .*\n)+"
        import_match = re.search(import_pattern, content)
        if import_match:
            insert_pos = import_match.end()
            content = content[:insert_pos] + import_block + content[insert_pos:]
            print("[INFO] Added required imports")
        else:
            print("[WARNING] Could not find import block; adding at top")
            content = import_block + content

    # 2. Locate and replace the ExposedDropdownMenu block
    start_idx = content.find("ExposedDropdownMenu(")
    if start_idx == -1:
        print("[ERROR] Could not find 'ExposedDropdownMenu(' in FormFields.kt")
        return content

    # Find the matching ')' for the parameters
    paren_depth = 0
    params_end = -1
    for i in range(start_idx + len("ExposedDropdownMenu("), len(content)):
        ch = content[i]
        if ch == '(':
            paren_depth += 1
        elif ch == ')':
            if paren_depth == 0:
                params_end = i
                break
            else:
                paren_depth -= 1
    if params_end == -1:
        print("[ERROR] Could not find closing ')' for ExposedDropdownMenu parameters")
        return content

    # Find the opening brace of the block after the ')'
    brace_pos = content.find("{", params_end)
    if brace_pos == -1:
        print("[ERROR] Could not find opening brace for ExposedDropdownMenu block")
        return content

    # Find matching closing brace
    block_end = find_matching_brace(content, brace_pos)
    if block_end == -1:
        print("[ERROR] Could not find closing brace for ExposedDropdownMenu block")
        return content

    # Replace the entire call from start_idx to block_end (inclusive)
    content = content[:start_idx] + NEW_DROPDOWN_BLOCK + content[block_end+1:]
    print("[INFO] Replaced ExposedDropdownMenu with searchable lazy version")

    return content


# ----------------------------------------------------------------------
# Main


def main(project_root):
    settings_path = os.path.join(project_root, SETTINGS_FILE)
    mmkv_path = os.path.join(project_root, MMKV_FILE)
    main_path = os.path.join(project_root, MAIN_ACTIVITY_FILE)
    form_path = os.path.join(project_root, FORM_FIELDS_FILE)

    for path in [settings_path, mmkv_path, main_path, form_path]:
        if not os.path.isfile(path):
            print(f"[ERROR] File not found: {path}")
            sys.exit(1)

    print("[INFO] Patching SettingsManager.kt...")
    content = read_file(settings_path)
    patched = patch_settings_manager(content)
    if content != patched:
        write_file(settings_path, patched)
        print("[INFO] SettingsManager.kt updated.")
    else:
        print("[INFO] No changes to SettingsManager.kt.")

    print("[INFO] Patching MmkvManager.kt...")
    content = read_file(mmkv_path)
    patched = patch_mmkv_manager(content)
    if content != patched:
        write_file(mmkv_path, patched)
        print("[INFO] MmkvManager.kt updated.")
    else:
        print("[INFO] No changes to MmkvManager.kt.")

    print("[INFO] Patching MainActivity.kt...")
    content = read_file(main_path)
    patched = patch_main_activity(content)
    if content != patched:
        write_file(main_path, patched)
        print("[INFO] MainActivity.kt updated.")
    else:
        print("[INFO] No changes to MainActivity.kt.")

    print("[INFO] Patching FormFields.kt...")
    content = read_file(form_path)
    patched = patch_form_fields(content)
    if content != patched:
        write_file(form_path, patched)
        print("[INFO] FormFields.kt updated.")
    else:
        print("[INFO] No changes to FormFields.kt.")

    print("[DONE] All patches applied. Rebuild and test.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fix_dropdown_final_working.py <project_root>")
        sys.exit(1)
    main(sys.argv[1])

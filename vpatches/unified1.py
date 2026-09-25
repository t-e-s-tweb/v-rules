#!/usr/bin/env python3
"""
v2rayNG patcher for self_use_build – aligned with upstream
  • DNS Parallel Query + Serve Stale toggles (strings + CoreConfigManager)
  • FormFields dropdown performance (typed filter + 50-item hard cap)

Idempotent.
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

def read(p):
    return p.read_text(encoding="utf-8")

def write(p, s):
    p.write_text(s, encoding="utf-8")


# ----------------------------------------------------------------------
# 1. strings.xml – DNS strings (may still be needed)
# ----------------------------------------------------------------------
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    if not p.exists():
        print("✗ strings.xml not found")
        return
    c = read(p)

    needed = {
        "title_dns_parallel_query": "DNS Parallel Query",
        "summary_dns_parallel_query": "Enable parallel queries to all DNS servers for faster resolution",
        "title_dns_serve_stale": "DNS Serve Stale",
        "summary_dns_serve_stale": "Serve stale DNS records while refreshing in background",
    }
    new_strings = []
    for k, v in needed.items():
        if f'name="{k}"' in c:
            continue
        new_strings.append(f'    <string name="{k}">{v}</string>')

    if not new_strings:
        print("• strings.xml: DNS strings already present")
        return

    m = re.search(r'(\s*)</resources>', c, re.IGNORECASE)
    if m:
        indent, pos = m.group(1), m.start()
        insertion = "\n" + "\n".join(new_strings) + "\n" + indent
        c = c[:pos] + insertion + c[pos:]
        write(p, c)
        print(f"✓ strings.xml: added {len(new_strings)} DNS strings")
    else:
        print("⚠ strings.xml: </resources> not found")


# ----------------------------------------------------------------------
# 2. CoreConfigManager.kt – set serveStale / enableParallelQuery on DnsBean
#    Upstream already has DnsBean fields; we just wire the prefs.
# ----------------------------------------------------------------------
def patch_coreconfigmanager_dns():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)

    # Find the live configureDns(configContext, v2rayConfig, policyGroupBalancerTags)
    sig = "private fun configureDns(\n        configContext: CoreConfigContext,"
    pos = c.find(sig)
    if pos == -1:
        # fallback: plain configureDns(v2rayConfig, policyGroupBalancerTags)
        sig = "private fun configureDns(\n        v2rayConfig: V2rayConfig,"
        pos = c.find(sig)
        if pos == -1:
            print("⚠ CoreConfigManager: no configureDns found")
            return
        print("• CoreConfigManager: using plain configureDns(v2rayConfig, …)")
    else:
        print("• CoreConfigManager: using live configureDns(configContext, …)")

    # Find the closing brace of the method
    open_brace = c.find('{', pos)
    if open_brace == -1:
        print("⚠ CoreConfigManager: no opening brace for configureDns")
        return

    brace_count = 1
    i = open_brace + 1
    while i < len(c) and brace_count > 0:
        if c[i] == '{':
            brace_count += 1
        elif c[i] == '}':
            brace_count -= 1
        i += 1
    if brace_count != 0:
        print("⚠ CoreConfigManager: brace mismatch in configureDns")
        return

    method_end = i
    method_body = c[pos:method_end]

    if "PREF_DNS_PARALLEL_QUERY" in method_body and "PREF_DNS_SERVE_STALE" in method_body:
        print("• CoreConfigManager: DNS prefs already wired")
        return

    backup_kotlin(p)

    # Upstream pattern: after the DnsBean construction block, insert pref checks.
    # Look for the DnsBean assignment.
    dns_assign_pat = re.compile(
        r'(v2rayConfig\.dns\s*=\s*V2rayConfig\.DnsBean\s*\([^)]*\))',
        re.DOTALL
    )
    m = dns_assign_pat.search(method_body)
    if not m:
        print("⚠ CoreConfigManager: DnsBean assignment not found inside configureDns")
        return

    dns_block = m.group(1)
    # Indentation: match the line that starts the assignment
    indent_match = re.search(r'^(\s*)v2rayConfig\.dns\s*=', method_body, re.MULTILINE)
    indent = indent_match.group(1) if indent_match else "        "

    injected = f'''
{indent}// DNS preference toggles (patched)
{indent}if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false) == true) {{
{indent}    v2rayConfig.dns?.serveStale = true
{indent}}}
{indent}if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false) == true) {{
{indent}    v2rayConfig.dns?.enableParallelQuery = true
{indent}}}'''

    new_body = method_body[:m.end()] + injected + method_body[m.end():]
    c = c[:pos] + new_body + c[method_end:]
    write(p, c)
    print("✓ CoreConfigManager: wired PREF_DNS_PARALLEL_QUERY + PREF_DNS_SERVE_STALE")


# ----------------------------------------------------------------------
# 3. FormFields.kt – typed filter + 50-item hard cap
#    Upstream FormDropdownField uses ExposedDropdownMenu with
#    options.forEach { option -> DropdownMenuItem(...) } (L67-72).
# ----------------------------------------------------------------------
def patch_formfields():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/compose/FormFields.kt"
    if not p.exists():
        print("✗ FormFields.kt not found")
        return
    c = read(p)

    # Drop stale lazy imports
    for stale in (
        "import androidx.compose.foundation.lazy.LazyColumn\n",
        "import androidx.compose.foundation.lazy.items\n",
        "import androidx.compose.foundation.lazy.rememberLazyListState\n",
    ):
        c = c.replace(stale, "")

    needed_imports = [
        "import androidx.compose.foundation.layout.heightIn",
        "import androidx.compose.runtime.remember",
    ]
    last_import = re.search(r'^import .*$', c, re.MULTILINE)
    if last_import:
        pos = last_import.end()
        missing = [imp for imp in needed_imports if imp not in c]
        if missing:
            c = c[:pos] + "\n" + "\n".join(missing) + c[pos:]
            print(f"✓ FormFields: added {len(missing)} import(s)")

    # State: filtered + capped list
    # Upstream state block ends with keyboardController (L48-49)
    old_state = '''    var expanded by rememberSaveable { mutableStateOf(false) }
    val menuScrollState = rememberScrollState()
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current'''
    new_state = '''    var expanded by rememberSaveable { mutableStateOf(false) }
    val menuScrollState = rememberScrollState()
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current

    // ExposedDropdownMenu can't host a LazyColumn (intrinsic measurement).
    // Keep the plain Column, filter by typed text, hard-cap at 50.
    val visibleOptions = remember(options, value, editable) {
        val base = if (editable && value.isNotBlank()) {
            options.filter { it.contains(value, ignoreCase = true) }
        } else {
            options
        }
        if (base.size > 50) base.take(50) else base
    }'''
    if "val visibleOptions = remember" in c:
        print("• FormFields: filtered/capped options already present")
    elif old_state in c:
        c = c.replace(old_state, new_state, 1)
        print("✓ FormFields: added typed-text filtering + 50-item cap")
    else:
        print("⚠ FormFields: state block not found")

    # Menu content — upstream pattern is options.forEach { option -> ... }
    # Replace with visibleOptions.forEach { ... }
    # Upstream ExposedDropdownMenu (L67-72) has:
    #   ExposedDropdownMenu(
    #       expanded = expanded,
    #       onDismissRequest = { expanded = false },
    #       modifier = Modifier.verticalScrollbar(menuScrollState),
    #       scrollState = menuScrollState,
    #       containerColor = MaterialTheme.colorScheme.surface
    #   ) {
    #       options.forEach { option ->
    #           DropdownMenuItem(
    #               text = { Text(option) },
    #               onClick = { onValueChange(option) expanded = false focusManager.clearFocus() }
    #           )
    #       }
    #   }
    old_menu = '''        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier.verticalScrollbar(menuScrollState),
            scrollState = menuScrollState,
            containerColor = MaterialTheme.colorScheme.surface
        ) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        onValueChange(option)
                        expanded = false
                        focusManager.clearFocus()
                    }
                )
            }
        }'''
    new_menu = '''        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier
                .verticalScrollbar(menuScrollState)
                .heightIn(max = 300.dp),
            scrollState = menuScrollState,
            containerColor = MaterialTheme.colorScheme.surface
        ) {
            visibleOptions.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        onValueChange(option)
                        expanded = false
                        focusManager.clearFocus()
                    }
                )
            }
        }'''

    if "visibleOptions.forEach" in c:
        print("• FormFields: dropdown menu already updated")
    elif old_menu in c:
        c = c.replace(old_menu, new_menu, 1)
        print("✓ FormFields: dropdown now uses filtered/capped list")
    else:
        # looser regex: just replace options.forEach with visibleOptions.forEach
        # and add heightIn to the modifier.
        c2 = re.sub(
            r'options\.forEach\s*\{\s*option\s*->',
            'visibleOptions.forEach { option ->',
            c
        )
        if c2 != c:
            c = c2
            # add heightIn to modifier if missing
            c = c.replace(
                'Modifier.verticalScrollbar(menuScrollState),\n            scrollState = menuScrollState,',
                'Modifier\n                .verticalScrollbar(menuScrollState)\n                .heightIn(max = 300.dp),\n            scrollState = menuScrollState,',
                1
            )
            print("✓ FormFields: dropdown updated (regex)")
        else:
            print("⚠ FormFields: ExposedDropdownMenu block not found")

    write(p, c)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Patcher: DNS Parallel/Serve-Stale + FormFields dropdowns")
    print("(aligned with upstream self_use_build)")
    print("=" * 70)
    try:
        patch_strings()
        patch_coreconfigmanager_dns()
        patch_formfields()
        print("\n✅ Done.")
        print("👉 Rebuild and test.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

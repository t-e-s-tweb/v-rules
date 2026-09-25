#!/usr/bin/env python3
"""
v2rayNG patcher for 2dust/v2rayNG master
  • DNS Parallel Query + Serve Stale toggles
  • FormFields dropdown performance (typed filter + 50-item hard cap)

Reference patches (DHR60/v2rayNG self_use_build):
  ec2d2da  perf. dns host
  fb3eb6c  Add DNS Parallel Query support
  acfaf1c  Fix DNS

Idempotent.
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path("V2rayNG")   # Android project folder inside the 2dust repo


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
# 1. AppConfig.kt – add DNS pref keys
# ----------------------------------------------------------------------
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    if not p.exists():
        print("✗ AppConfig.kt not found")
        return
    c = read(p)

    if "PREF_DNS_PARALLEL_QUERY" in c and "PREF_DNS_SERVE_STALE" in c:
        print("• AppConfig: DNS pref keys already present")
        return

    old = '    const val PREF_DNS_HOSTS = "pref_dns_hosts"'
    new = '''    const val PREF_DNS_HOSTS = "pref_dns_hosts"
    const val PREF_DNS_PARALLEL_QUERY = "pref_dns_parallel_query"
    const val PREF_DNS_SERVE_STALE = "pref_dns_serve_stale"'''
    if old in c:
        c = c.replace(old, new, 1)
        write(p, c)
        print("✓ AppConfig: added PREF_DNS_PARALLEL_QUERY + PREF_DNS_SERVE_STALE")
    else:
        print("⚠ AppConfig: PREF_DNS_HOSTS declaration not found")


# ----------------------------------------------------------------------
# 2. V2rayConfig.kt – add serveStale to DnsBean
# ----------------------------------------------------------------------
def patch_v2rayconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/V2rayConfig.kt"
    if not p.exists():
        print("✗ V2rayConfig.kt not found")
        return
    c = read(p)

    if "var serveStale" in c or "val serveStale" in c:
        print("• V2rayConfig: serveStale already present")
        return

    # Exact literal first
    old_dns = '''data class DnsBean(
        var servers: ArrayList<Any>? = null,
        var hosts: Map<String, Any>? = null,
        val clientIp: String? = null,
        val disableCache: Boolean? = null,
        val queryStrategy: String? = null,
        val enableParallelQuery: Boolean? = null,
        val tag: String? = null
    )'''
    new_dns = '''data class DnsBean(
        var servers: ArrayList<Any>? = null,
        var hosts: Map<String, Any>? = null,
        val clientIp: String? = null,
        val disableCache: Boolean? = null,
        val queryStrategy: String? = null,
        val enableParallelQuery: Boolean? = null,
        val tag: String? = null,
        var serveStale: Boolean? = null
    )'''
    if old_dns in c:
        c = c.replace(old_dns, new_dns, 1)
        write(p, c)
        print("✓ V2rayConfig: added serveStale to DnsBean")
        return

    # Tolerant regex fallback
    m = re.search(
        r'(data class DnsBean\s*\(.*?val tag: String\? = null)\s*\)',
        c, re.DOTALL
    )
    if m:
        replacement = m.group(1) + ',\n        var serveStale: Boolean? = null\n    )'
        c = c[:m.start()] + replacement + c[m.end():]
        write(p, c)
        print("✓ V2rayConfig: added serveStale (regex)")
    else:
        print("⚠ V2rayConfig: DnsBean not matched")


# ----------------------------------------------------------------------
# 3. CoreConfigManager.kt – append pref checks at end of configureDns
#    Upstream does NOT construct DnsBean here; it only mutates the
#    already-parsed v2rayConfig.dns via safe-call. So we do the same.
# ----------------------------------------------------------------------
def patch_coreconfigmanager_dns():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)

    if "PREF_DNS_PARALLEL_QUERY" in c and "PREF_DNS_SERVE_STALE" in c:
        print("• CoreConfigManager: DNS prefs already wired")
        return

    # Locate the method definition
    sig = "private fun configureDns(\n        v2rayConfig: V2rayConfig,"
    pos = c.find(sig)
    if pos == -1:
        # Looser fallback: allow any whitespace between params
        m_sig = re.search(
            r'private fun configureDns\(\s*v2rayConfig\s*:\s*V2rayConfig\s*,',
            c
        )
        if not m_sig:
            print("⚠ CoreConfigManager: configureDns(v2rayConfig, …) not found")
            return
        pos = m_sig.start()
        sig = c[pos:m_sig.end()]

    open_brace = c.find('{', pos)
    if open_brace == -1:
        print("⚠ CoreConfigManager: no opening brace for configureDns")
        return

    # Match braces to find the method end
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

    insert_at = i - 1  # position of the closing brace

    # Derive indentation from the first body line
    body_start = open_brace + 1
    line_start = c.rfind('\n', 0, body_start) + 1
    indent = c[line_start:body_start]
    if not indent.strip():
        indent = "        "  # 8 spaces – matches Kotlin convention in this file

    backup_kotlin(p)

    injected = f'''
{indent}// DNS toggles (patched)
{indent}if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false) == true) {{
{indent}    v2rayConfig.dns?.serveStale = true
{indent}}}
{indent}if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false) == true) {{
{indent}    v2rayConfig.dns?.enableParallelQuery = true
{indent}}}
'''

    c = c[:insert_at] + injected + c[insert_at:]
    write(p, c)
    print("✓ CoreConfigManager: wired PREF_DNS_PARALLEL_QUERY + PREF_DNS_SERVE_STALE")


# ----------------------------------------------------------------------
# 4. SettingsActivity.kt – add DNS state + switches
# ----------------------------------------------------------------------
def patch_settings():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/settings/SettingsActivity.kt"
    if not p.exists():
        print("✗ SettingsActivity.kt not found")
        return
    c = read(p)

    # 4a. State declarations
    old_decl = 'var dnsHosts by rememberMmkvString(AppConfig.PREF_DNS_HOSTS, "")'
    new_decl = old_decl + """
    var dnsParallelQuery by rememberMmkvBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false)
    var dnsServeStale by rememberMmkvBool(AppConfig.PREF_DNS_SERVE_STALE, false)"""
    if "dnsParallelQuery" in c:
        print("• SettingsActivity: DNS states already present")
    elif old_decl in c:
        c = c.replace(old_decl, new_decl, 1)
        print("✓ SettingsActivity: added DNS parallel/stale state")
    else:
        print("⚠ SettingsActivity: dnsHosts declaration not found")

    # 4b. UI switches – insert after the dnsHosts SettingsEditItem block
    if "title_pref_dns_parallel_query" in c:
        print("• SettingsActivity: switches already present")
    else:
        pattern = (
            r'(SettingsEditItem\(\s*'
            r'title = stringResource\(R\.string\.title_pref_dns_hosts\),\s*'
            r'value = dnsHosts,\s*'
            r'onValueChanged = \{ dnsHosts = it \}\s*'
            r'\))'
        )
        replacement = r'''\1
                SettingsSwitchItem(
                    title = stringResource(R.string.title_pref_dns_parallel_query),
                    summary = stringResource(R.string.summary_pref_dns_parallel_query),
                    checked = dnsParallelQuery,
                    onCheckedChange = { dnsParallelQuery = it }
                )
                SettingsSwitchItem(
                    title = stringResource(R.string.title_pref_dns_serve_stale),
                    summary = stringResource(R.string.summary_pref_dns_serve_stale),
                    checked = dnsServeStale,
                    onCheckedChange = { dnsServeStale = it }
                )'''
        new_c, n = re.subn(pattern, replacement, c, flags=re.DOTALL)
        if n:
            c = new_c
            print("✓ SettingsActivity: inserted DNS parallel/stale switches")
        else:
            print("⚠ SettingsActivity: dnsHosts SettingsEditItem block not found")

    write(p, c)


# ----------------------------------------------------------------------
# 5. strings.xml – DNS strings
# ----------------------------------------------------------------------
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    if not p.exists():
        print("✗ strings.xml not found")
        return
    c = read(p)

    needed = {
        "title_pref_dns_parallel_query": "DNS Parallel Query",
        "summary_pref_dns_parallel_query": "Enable parallel queries to all DNS servers for faster resolution",
        "title_pref_dns_serve_stale": "DNS Serve Stale",
        "summary_pref_dns_serve_stale": "Serve stale DNS records while refreshing in background",
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
# 6. FormFields.kt – typed filter + 50-item hard cap
#    Keeps the plain Column that ExposedDropdownMenu needs (LazyColumn
#    crashes on intrinsic measurement).
# ----------------------------------------------------------------------
def patch_formfields():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/compose/FormFields.kt"
    if not p.exists():
        print("✗ FormFields.kt not found")
        return
    c = read(p)

    # Drop stale lazy imports from previous attempts
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

    # Menu content
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
        # Loose fallback: swap options -> visibleOptions and add heightIn
        c2 = re.sub(
            r'options\.forEach\s*\{\s*option\s*->',
            'visibleOptions.forEach { option ->',
            c
        )
        if c2 != c:
            c = c2
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
    print("Patcher for 2dust/v2rayNG – DNS Parallel/Serve-Stale + FormFields")
    print("=" * 70)
    try:
        patch_appconfig()
        patch_v2rayconfig()
        patch_coreconfigmanager_dns()
        patch_settings()
        patch_strings()
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

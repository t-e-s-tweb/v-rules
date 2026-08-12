#!/usr/bin/env python3
"""
Minimal v2rayNG patcher – only:

  • DNS Parallel Query + Serve Stale toggles
  • FormFields dropdown performance (typed filter + 50-item hard cap)

Skips: CURRENT_SERVER / chain helpers, custom outbound injection,
       DHR60 configContext DNS revert, etc.

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
# 1. AppConfig.kt – DNS prefs only
# ----------------------------------------------------------------------
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    if not p.exists():
        print("✗ AppConfig.kt not found")
        return
    c = read(p)

    if "PREF_DNS_PARALLEL_QUERY" in c and "PREF_DNS_SERVE_STALE" in c:
        print("• AppConfig: DNS prefs already present")
        return

    old = '    const val PREF_DNS_HOSTS = "pref_dns_hosts"'
    new = '''    const val PREF_DNS_HOSTS = "pref_dns_hosts"
    const val PREF_DNS_PARALLEL_QUERY = "pref_dns_parallel_query"
    const val PREF_DNS_SERVE_STALE = "pref_dns_serve_stale"'''
    if old in c:
        c = c.replace(old, new, 1)
        print("✓ AppConfig: added PREF_DNS_PARALLEL_QUERY + PREF_DNS_SERVE_STALE")
    else:
        print("⚠ AppConfig: PREF_DNS_HOSTS not found, skipping DNS prefs")
        return
    write(p, c)


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
        print("✓ V2rayConfig: added serveStale to DnsBean")
    else:
        # more tolerant match
        m = re.search(
            r'data class DnsBean\s*\(\s*'
            r'var servers:.*?'
            r'val enableParallelQuery: Boolean\? = null,\s*'
            r'val tag: String\? = null\s*'
            r'\)',
            c, re.DOTALL
        )
        if m:
            replacement = m.group(0).rstrip()[:-1] + ',\n        var serveStale: Boolean? = null\n    )'
            c = c[:m.start()] + replacement + c[m.end():]
            print("✓ V2rayConfig: added serveStale (regex)")
        else:
            print("⚠ V2rayConfig: DnsBean not found, skipping")
            return
    write(p, c)


# ----------------------------------------------------------------------
# 3. strings.xml – only the two DNS strings
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
# 4. CoreConfigManager.kt – wire prefs into whichever configureDns is live
# ----------------------------------------------------------------------
def patch_coreconfigmanager_dns():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)

    # Prefer the live configContext-based one; fall back to the plain one
    live_sig = "private fun configureDns(\n        configContext: CoreConfigContext,"
    plain_sig = "private fun configureDns(\n        v2rayConfig: V2rayConfig,"

    method_start = c.find(live_sig)
    if method_start == -1:
        method_start = c.find(plain_sig)
        if method_start == -1:
            print("⚠ CoreConfigManager: no configureDns found")
            return
        print("• CoreConfigManager: using plain configureDns(v2rayConfig, …)")
    else:
        print("• CoreConfigManager: using live configureDns(configContext, …)")

    open_brace = c.find('{', method_start)
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
    method_body = c[method_start:method_end]

    if "PREF_DNS_PARALLEL_QUERY" in method_body and "PREF_DNS_SERVE_STALE" in method_body:
        print("• CoreConfigManager: DNS prefs already wired")
        return

    backup_kotlin(p)

    old_dns_construction = '''v2rayConfig.dns = V2rayConfig.DnsBean(
            servers = servers,
            hosts = hosts,
            tag = AppConfig.TAG_DNS,
            enableParallelQuery = if ((domesticDns.size + remoteDns.size) > 2) true else null
        )'''
    new_dns_construction = '''val dnsParallelQueryEnabled = MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false)
        val dnsServeStaleEnabled = MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false)

        v2rayConfig.dns = V2rayConfig.DnsBean(
            servers = servers,
            hosts = hosts,
            tag = AppConfig.TAG_DNS,
            enableParallelQuery = if (dnsParallelQueryEnabled) true else null,
            serveStale = if (dnsServeStaleEnabled) true else null
        )'''

    if old_dns_construction in method_body:
        new_method_body = method_body.replace(old_dns_construction, new_dns_construction, 1)
        c = c[:method_start] + new_method_body + c[method_end:]
        print("✓ CoreConfigManager: wired PREF_DNS_PARALLEL_QUERY + PREF_DNS_SERVE_STALE")
    else:
        # looser regex
        pat = re.compile(
            r'v2rayConfig\.dns\s*=\s*V2rayConfig\.DnsBean\s*\(\s*'
            r'servers\s*=\s*servers\s*,\s*'
            r'hosts\s*=\s*hosts\s*,\s*'
            r'tag\s*=\s*AppConfig\.TAG_DNS\s*,\s*'
            r'enableParallelQuery\s*=\s*if\s*\(\(domesticDns\.size\s*\+\s*remoteDns\.size\)\s*>\s*2\)\s*true\s*else\s*null\s*'
            r'\)',
            re.DOTALL
        )
        if pat.search(method_body):
            new_method_body = pat.sub(new_dns_construction.strip(), method_body, count=1)
            c = c[:method_start] + new_method_body + c[method_end:]
            print("✓ CoreConfigManager: wired via regex")
        else:
            print("⚠ CoreConfigManager: DnsBean construction not found inside configureDns")
            return

    write(p, c)


# ----------------------------------------------------------------------
# 5. SettingsActivity.kt – the two switches
# ----------------------------------------------------------------------
def patch_settings():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/settings/SettingsActivity.kt"
    if not p.exists():
        print("✗ SettingsActivity.kt not found")
        return
    c = read(p)

    # state declarations
    old_decls = 'var dnsHosts by rememberMmkvString(AppConfig.PREF_DNS_HOSTS, "")'
    new_decls = old_decls + """
    var dnsParallelQuery by rememberMmkvBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false)
    var dnsServeStale by rememberMmkvBool(AppConfig.PREF_DNS_SERVE_STALE, false)"""
    if "dnsParallelQuery" in c:
        print("• SettingsActivity: DNS states already present")
    elif old_decls in c:
        c = c.replace(old_decls, new_decls, 1)
        print("✓ SettingsActivity: added DNS parallel/stale state")
    else:
        print("⚠ SettingsActivity: dnsHosts declaration not found")

    # UI switches
    if "title_pref_dns_parallel_query" in c:
        print("• SettingsActivity: switches already present")
    else:
        pattern = r'(SettingsEditItem\(\s*title = stringResource\(R\.string\.title_pref_dns_hosts\),\s*value = dnsHosts,\s*onValueChanged = \{ dnsHosts = it \}\s*\))'
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
# 6. FormFields.kt – typed filter + 50-item hard cap (no LazyColumn)
# ----------------------------------------------------------------------
def patch_formfields():
    """
    Keep the plain Column that ExposedDropdownMenu requires (LazyColumn
    crashes on intrinsic measurement). Bound what it renders by filtering
    on typed text + a hard cap of 50.
    """
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/compose/FormFields.kt"
    if not p.exists():
        print("✗ FormFields.kt not found")
        return
    c = read(p)

    # drop any leftover lazy imports from a previous attempt
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

    # state: filtered + capped list
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

    # menu content
    pristine_menu = '''        ExposedDropdownMenu(
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
    lazy_menu_from_v1 = '''        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier
                .verticalScrollbar(menuScrollState)
                .heightIn(max = 300.dp),
            scrollState = menuScrollState,
            containerColor = MaterialTheme.colorScheme.surface
        ) {
            val lazyListState = rememberLazyListState()
            LazyColumn(
                state = lazyListState,
                modifier = Modifier
                    .heightIn(max = 300.dp)
                    .verticalScrollbar(lazyListState)
            ) {
                items(options) { option ->
                    DropdownMenuItem(
                        text = { Text(option) },
                        onClick = {
                            onValueChange(option)
                            expanded = false
                            focusManager.clearFocus()
                        }
                    )
                }
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
    elif pristine_menu in c:
        c = c.replace(pristine_menu, new_menu, 1)
        print("✓ FormFields: dropdown now uses filtered/capped list")
    elif lazy_menu_from_v1 in c:
        c = c.replace(lazy_menu_from_v1, new_menu, 1)
        print("↺ FormFields: reverted LazyColumn attempt → filtering")
    else:
        print("⚠ FormFields: ExposedDropdownMenu block not found")

    write(p, c)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Minimal patcher: DNS Parallel/Serve-Stale + FormFields dropdowns")
    print("=" * 70)
    try:
        patch_appconfig()
        patch_v2rayconfig()
        patch_strings()
        patch_coreconfigmanager_dns()
        patch_settings()
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

#!/usr/bin/env python3
"""
v2rayNG patcher for 2dust/v2rayNG master
  • DNS Parallel Query + Serve Stale toggles       (DHR60 fb3eb6c)
  • DNS server ordering fix in configureDns       (DHR60 acfaf1c)
  • WireGuard remoteDNS fallback split fix         (ParseAddr panic)
  • FormFields dropdown performance                (typed filter + 50-cap)

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
# 1. AppConfig.kt – DNS pref keys
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
        var enableParallelQuery: Boolean? = null,
        val tag: String? = null,
        var serveStale: Boolean? = null
    )'''
    if old_dns in c:
        c = c.replace(old_dns, new_dns, 1)
        write(p, c)
        print("✓ V2rayConfig: added serveStale to DnsBean")
        return

    # Tolerant fallback: match DnsBean ending with tag = String? = null
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
# 3. CoreConfigManager.kt
#    3a. DNS ordering fix (acfaf1c): move remoteDns.forEach after domestic
#    3b. Wire in PREF_DNS_PARALLEL_QUERY / PREF_DNS_SERVE_STALE (fb3eb6c)
# ----------------------------------------------------------------------
def patch_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)

    changed = False
    backup_kotlin(p)

    # ---- 3a. DNS ordering fix ----
    # Move `remoteDns.forEach { servers.add(it) }` to after the
    # domestic DNS block (before the DnsBean assignment or method end).
    remote_line = "        remoteDns.forEach { servers.add(it) }"
    if remote_line in c and "// (dns-order-fixed)" not in c:
        # Remove the original occurrence
        c = c.replace(remote_line + "\n", "", 1)

        # Re-insert after the domestic DNS / cnRouting block.
        # Anchor: just before `v2rayConfig.dns =` OR before the method's
        # closing brace if no DnsBean assignment exists.
        anchor_pat = re.compile(
            r'(\n\s*v2rayConfig\.dns\s*=\s*V2rayConfig\.DnsBean)'
        )
        m_anchor = anchor_pat.search(c)
        if m_anchor:
            insert_at = m_anchor.start()
        else:
            # Fall back to end of configureDns
            sig = "private fun configureDns("
            pos = c.find(sig)
            if pos == -1:
                print("⚠ CoreConfigManager: configureDns not found for reorder")
                write(p, c)
                return
            open_brace = c.find('{', pos)
            brace_count = 1
            i = open_brace + 1
            while i < len(c) and brace_count > 0:
                if c[i] == '{':
                    brace_count += 1
                elif c[i] == '}':
                    brace_count -= 1
                i += 1
            insert_at = i - 1

        c = (
            c[:insert_at]
            + "\n        // (dns-order-fixed)\n"
            + remote_line
            + "\n"
            + c[insert_at:]
        )
        changed = True
        print("✓ CoreConfigManager: remoteDns added after domestic DNS")
    elif "// (dns-order-fixed)" in c:
        print("• CoreConfigManager: DNS ordering already fixed")

    # ---- 3b. Serve-stale / parallel-query pref wiring ----
    if "PREF_DNS_PARALLEL_QUERY" not in c or "PREF_DNS_SERVE_STALE" not in c:
        # Try to inject after the DnsBean assignment
        dns_pat = re.compile(
            r'(v2rayConfig\.dns\s*=\s*V2rayConfig\.DnsBean\s*\(.*?\))',
            re.DOTALL
        )
        m = dns_pat.search(c)
        if m:
            line_start = c.rfind('\n', 0, m.start()) + 1
            indent = c[line_start:m.start()]
            injected = f'''
{indent}// DNS toggles (patched)
{indent}if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false) == true) {{
{indent}    v2rayConfig.dns?.serveStale = true
{indent}}}
{indent}if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false) == true) {{
{indent}    v2rayConfig.dns?.enableParallelQuery = true
{indent}}}'''
            c = c[:m.end()] + injected + c[m.end():]
            changed = True
            print("✓ CoreConfigManager: wired PREF_DNS_PARALLEL_QUERY + PREF_DNS_SERVE_STALE")
        else:
            # No DnsBean assignment in this file – inject at end of configureDns
            sig = "private fun configureDns("
            pos = c.find(sig)
            if pos == -1:
                print("⚠ CoreConfigManager: configureDns not found for pref wiring")
            else:
                open_brace = c.find('{', pos)
                brace_count = 1
                i = open_brace + 1
                while i < len(c) and brace_count > 0:
                    if c[i] == '{':
                        brace_count += 1
                    elif c[i] == '}':
                        brace_count -= 1
                    i += 1
                insert_at = i - 1
                line_start = c.rfind('\n', 0, open_brace + 1) + 1
                indent = c[line_start:open_brace + 1]
                if not indent.strip():
                    indent = "        "
                injected = f'''
{indent}// DNS toggles (patched)
{indent}if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false) == true) {{
{indent}    v2rayConfig.dns?.serveStale = true
{indent}}}
{indent}if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false) == true) {{
{indent}    v2rayConfig.dns?.enableParallelQuery = true
{indent}}}'''
                c = c[:insert_at] + injected + c[insert_at:]
                changed = True
                print("✓ CoreConfigManager: wired DNS prefs at end of configureDns")
    else:
        print("• CoreConfigManager: DNS prefs already wired")

    if changed:
        write(p, c)


# ----------------------------------------------------------------------
# 4. CoreOutboundBuilder.kt – WireGuard remoteDNS fallback split
#    Fixes: panic: ParseAddr("1.1.1.1,1.0.0.1,...")
#    The fallback listOf(AppConfig.WIREGUARD_LOCAL_REMOTE_DNS) puts the
#    whole comma-separated string into a single list element.
# ----------------------------------------------------------------------
def patch_wireguard_remotedns():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreOutboundBuilder.kt"
    if not p.exists():
        print("✗ CoreOutboundBuilder.kt not found")
        return
    c = read(p)

    old_fallback = "?: listOf(AppConfig.WIREGUARD_LOCAL_REMOTE_DNS)"
    new_fallback = (
        "?: AppConfig.WIREGUARD_LOCAL_REMOTE_DNS"
        ".split(\",\").map { it.trim() }.filter { it.isNotEmpty() }"
    )

    if new_fallback in c:
        print("• CoreOutboundBuilder: WireGuard remoteDNS fallback already fixed")
        return

    if old_fallback in c:
        backup_kotlin(p)
        c = c.replace(old_fallback, new_fallback, 1)
        write(p, c)
        print("✓ CoreOutboundBuilder: split WIREGUARD_LOCAL_REMOTE_DNS fallback")
    else:
        # Looser: the fallback may span lines
        m = re.search(
            r'\?:\s*listOf\(\s*AppConfig\.WIREGUARD_LOCAL_REMOTE_DNS\s*\)',
            c
        )
        if m:
            backup_kotlin(p)
            c = c[:m.start()] + new_fallback + c[m.end():]
            write(p, c)
            print("✓ CoreOutboundBuilder: split fallback (regex)")
        else:
            print("⚠ CoreOutboundBuilder: remoteDNS fallback pattern not found")


# ----------------------------------------------------------------------
# 5. SettingsActivity.kt – DNS state + switches
# ----------------------------------------------------------------------
def patch_settings():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/settings/SettingsActivity.kt"
    if not p.exists():
        print("✗ SettingsActivity.kt not found")
        return
    c = read(p)

    # 5a. State declarations
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

    # 5b. UI switches – insert after dnsHosts SettingsEditItem
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
# 6. strings.xml – DNS strings
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
# 7. FormFields.kt – typed filter + 50-item hard cap
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
        # Loose fallback
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
    print("Patcher: DNS toggles + DNS ordering + WireGuard remoteDNS + FormFields")
    print("=" * 70)
    try:
        patch_appconfig()
        patch_v2rayconfig()
        patch_coreconfigmanager()
        patch_wireguard_remotedns()
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

#!/usr/bin/env python3
"""
v2rayNG patcher for 2dust/v2rayNG master
  • DNS Parallel Query + Serve Stale toggles       (DHR60 fb3eb6c)
  • DNS hosts multi-IP format                     (DHR60 ec2d2da)
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
        print("✓ AppConfig: added DNS pref keys")
    else:
        print("⚠ AppConfig: PREF_DNS_HOSTS not found")


# ----------------------------------------------------------------------
# 2. V2rayConfig.kt – enableParallelQuery val → var, add serveStale
# ----------------------------------------------------------------------
def patch_v2rayconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/V2rayConfig.kt"
    if not p.exists():
        print("✗ V2rayConfig.kt not found")
        return
    c = read(p)
    changed = False
    if re.search(r'val\s+enableParallelQuery\s*:\s*Boolean\?', c):
        c = re.sub(r'val\s+enableParallelQuery\s*:\s*Boolean\?',
                   'var enableParallelQuery: Boolean?', c)
        changed = True
        print("✓ V2rayConfig: enableParallelQuery val -> var")
    else:
        print("• V2rayConfig: enableParallelQuery already var or missing")
    if "serveStale" in c:
        print("• V2rayConfig: serveStale already present")
    else:
        m = re.search(r'(data class DnsBean\s*\(.*?val tag: String\? = null)\s*\)',
                      c, re.DOTALL)
        if m:
            c = (c[:m.end(1)]
                 + ',\n        var serveStale: Boolean? = null\n    )'
                 + c[m.end():])
            changed = True
            print("✓ V2rayConfig: added serveStale to DnsBean")
        else:
            print("⚠ V2rayConfig: DnsBean not matched")
    if changed:
        backup_kotlin(p)
        write(p, c)


# ----------------------------------------------------------------------
# 3. CoreConfigManager.kt – DnsBean pref-driven
# ----------------------------------------------------------------------
def patch_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)
    if "// (dns-prefs-injected)" in c:
        print("• CoreConfigManager: DNS prefs already injected")
        return
    old = (
        "        v2rayConfig.dns = V2rayConfig.DnsBean(\n"
        "            servers = servers,\n"
        "            hosts = hosts,\n"
        "            tag = AppConfig.TAG_DNS,\n"
        "            enableParallelQuery = if ((domesticDns.size + remoteDns.size) > 2) true else null\n"
        "        )"
    )
    new = (
        "        // (dns-prefs-injected)\n"
        "        v2rayConfig.dns = V2rayConfig.DnsBean(\n"
        "            servers = servers,\n"
        "            hosts = hosts,\n"
        "            tag = AppConfig.TAG_DNS,\n"
        "            enableParallelQuery = if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false)) true else null,\n"
        "            serveStale = if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false)) true else null\n"
        "        )"
    )
    if old in c:
        backup_kotlin(p)
        c = c.replace(old, new, 1)
        write(p, c)
        print("✓ CoreConfigManager: DnsBean rewritten with pref-driven fields")
    else:
        print("⚠ CoreConfigManager: exact DnsBean literal not found")


# ----------------------------------------------------------------------
# 4. CoreConfigManager.kt – DNS hosts multi-IP format (DHR60 ec2d2da)
#    Replaces the comma/first-colon parser in the live
#    buildDnsHostsFromRoutingRules with a line-based parser that
#    accepts multiple space-separated IPs per domain.
# ----------------------------------------------------------------------
def patch_dns_hosts_format():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    c = read(p)

    if "// (dns-hosts-multi-ip)" in c:
        print("• CoreConfigManager: DNS hosts multi-IP format already applied")
        return

    old = r'''        val userHosts = MmkvManager.decodeSettingsString(AppConfig.PREF_DNS_HOSTS)
        if (userHosts.isNotNullEmpty()) {
            val userHostsMap = userHosts?.split(",").orEmpty()
                .filter { it.isNotBlank() && it.contains(":") }
                .associate {
                    // Use limit = 2 to split only at the first colon.
                    // This ensures that IPv6 addresses (which contain multiple colons)
                    // are preserved entirely in the second part.
                    val parts = it.split(":", limit = 2)
                    parts[0].trim() to parts[1].trim()
                }
            hosts.putAll(userHostsMap)
        }'''

    new = r'''        // (dns-hosts-multi-ip)
        val userHosts = MmkvManager.decodeSettingsString(AppConfig.PREF_DNS_HOSTS)
        if (userHosts.isNotNullEmpty()) {
            val userHostsMap = userHosts?.lines()
                ?.filter { it.isNotEmpty() }
                ?.filter { it.contains(" ") }
                ?.associate { line ->
                    val parts = line.trim().split("\\s+".toRegex())
                    val key = parts[0]
                    val values = parts.drop(1)
                    key to if (values.size == 1) values[0] else values
                }
            if (userHostsMap != null) hosts.putAll(userHostsMap)
        }'''

    if old in c:
        backup_kotlin(p)
        c = c.replace(old, new, 1)
        write(p, c)
        print("✓ CoreConfigManager: DNS hosts parser rewritten (multi-IP, line-based)")
    else:
        print("⚠ CoreConfigManager: live userHosts parser not found — "
              "upstream may have reformatted it")


# ----------------------------------------------------------------------
# 5. strings.xml – update the DNS hosts field hint
# ----------------------------------------------------------------------
def patch_dns_hosts_hint():
    targets = {
        BASE / "app/src/main/res/values/strings.xml": (
            'DNS hosts (format: "domain address1 address2", one per line)'
            r'\ndomain address1 address2'
        ),
        BASE / "app/src/main/res/values-zh-rCN/strings.xml": (
            'DNS hosts (格式: "域名 地址1 地址2" 每行一个)'
            r'\ndomain address1 address2'
        ),
    }
    pat = re.compile(r'<string name="title_pref_dns_hosts">.*?</string>', re.DOTALL)

    for p, value in targets.items():
        if not p.exists():
            print(f"• {p.name}: not present, skipping")
            continue
        c = read(p)
        m = pat.search(c)
        if not m:
            print(f"⚠ {p.name}: title_pref_dns_hosts not found")
            continue
        new = f'<string name="title_pref_dns_hosts">{value}</string>'
        if m.group(0) == new:
            print(f"• {p.name}: hint already updated")
            continue
        c = pat.sub(new, c, count=1)
        write(p, c)
        print(f"✓ {p.name}: updated title_pref_dns_hosts hint")


# ----------------------------------------------------------------------
# 6. CoreOutboundBuilder.kt – WireGuard remoteDNS fallback split
# ----------------------------------------------------------------------
def patch_wireguard_remotedns():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreOutboundBuilder.kt"
    if not p.exists():
        print("✗ CoreOutboundBuilder.kt not found")
        return
    c = read(p)
    old1 = "?: listOf(AppConfig.WIREGUARD_LOCAL_REMOTE_DNS)"
    new1 = ('?: AppConfig.WIREGUARD_LOCAL_REMOTE_DNS'
            '.split(",").map { it.trim() }.filter { it.isNotEmpty() }')
    old2 = "listOf(AppConfig.WIREGUARD_LOCAL_REMOTE_DNS)"
    if new1 in c:
        print("• CoreOutboundBuilder: fallback already fixed")
        return
    if old1 in c:
        backup_kotlin(p)
        c = c.replace(old1, new1, 1)
        write(p, c)
        print("✓ CoreOutboundBuilder: split fallback")
    elif old2 in c:
        backup_kotlin(p)
        c = c.replace(old2,
                      'AppConfig.WIREGUARD_LOCAL_REMOTE_DNS'
                      '.split(",").map { it.trim() }.filter { it.isNotEmpty() }', 1)
        write(p, c)
        print("✓ CoreOutboundBuilder: split fallback")
    else:
        print("⚠ CoreOutboundBuilder: fallback pattern not found")


# ----------------------------------------------------------------------
# 7. SettingsActivity.kt – DNS state + switches
# ----------------------------------------------------------------------
def patch_settings():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/settings/SettingsActivity.kt"
    if not p.exists():
        print("✗ SettingsActivity.kt not found")
        return
    c = read(p)

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
            print("✓ SettingsActivity: inserted DNS switches")
        else:
            print("⚠ SettingsActivity: dnsHosts SettingsEditItem not found")

    write(p, c)


# ----------------------------------------------------------------------
# 8. strings.xml – DNS pref strings
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
        c = c[:pos] + "\n" + "\n".join(new_strings) + "\n" + indent + c[pos:]
        write(p, c)
        print(f"✓ strings.xml: added {len(new_strings)} DNS strings")
    else:
        print("⚠ strings.xml: </resources> not found")


# ----------------------------------------------------------------------
# 9. FormFields.kt – typed filter + 50-item hard cap
# ----------------------------------------------------------------------
def patch_formfields():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/compose/FormFields.kt"
    if not p.exists():
        print("✗ FormFields.kt not found")
        return
    c = read(p)

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
        print("✓ FormFields: added filtering + 50-item cap")
    else:
        print("⚠ FormFields: state block not found")

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
        print("• FormFields: dropdown already updated")
    elif old_menu in c:
        c = c.replace(old_menu, new_menu, 1)
        print("✓ FormFields: dropdown uses filtered/capped list")
    else:
        c2 = re.sub(r'options\.forEach\s*\{\s*option\s*->',
                    'visibleOptions.forEach { option ->', c)
        if c2 != c:
            c = c2
            c = c.replace(
                'Modifier.verticalScrollbar(menuScrollState),\n            scrollState = menuScrollState,',
                'Modifier\n                .verticalScrollbar(menuScrollState)\n                .heightIn(max = 300.dp),\n            scrollState = menuScrollState,',
                1)
            print("✓ FormFields: dropdown updated (regex)")
        else:
            print("⚠ FormFields: ExposedDropdownMenu block not found")
    write(p, c)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Patcher: DNS toggles + DNS hosts multi-IP + WireGuard + FormFields")
    print("=" * 70)
    try:
        patch_appconfig()
        patch_v2rayconfig()
        patch_coreconfigmanager()
        patch_dns_hosts_format()
        patch_dns_hosts_hint()
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

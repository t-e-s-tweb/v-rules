#!/usr/bin/env python3
"""
Final Fixed Unified Patcher – DNS working + Fast Dropdowns (Build Errors Fixed)
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
# 1. AppConfig.kt
# ----------------------------------------------------------------------
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    c = read(p)

    if '"__CURRENT_SERVER__"' not in c:
        marker = "    val BUILTIN_OUTBOUND_TAGS = setOf("
        if marker in c:
            insert_pos = c.find(marker) + len(marker)
            brace_count = 1
            i = insert_pos
            while i < len(c) and brace_count > 0:
                if c[i] == '(': brace_count += 1
                elif c[i] == ')': brace_count -= 1
                i += 1
            const_line = '\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"'
            c = c[:i] + const_line + c[i:]
            print("✓ AppConfig: added CURRENT_SERVER")
        else:
            last_brace = c.rfind('}')
            if last_brace != -1:
                c = c[:last_brace] + '\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"\n' + c[last_brace:]
                print("✓ AppConfig: added CURRENT_SERVER (fallback)")

    if "PREF_DNS_PARALLEL_QUERY" not in c:
        old = '    const val PREF_DNS_HOSTS = "pref_dns_hosts"'
        new = '''    const val PREF_DNS_HOSTS = "pref_dns_hosts"
    const val PREF_DNS_PARALLEL_QUERY = "pref_dns_parallel_query"
    const val PREF_DNS_SERVE_STALE = "pref_dns_serve_stale"'''
        c = c.replace(old, new, 1)
        print("✓ AppConfig: added DNS prefs")

    write(p, c)


# ----------------------------------------------------------------------
# 2. V2rayConfig.kt
# ----------------------------------------------------------------------
def patch_v2rayconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/V2rayConfig.kt"
    c = read(p)
    if "var serveStale" in c:
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
        print("⚠ V2rayConfig: DnsBean not found")
    write(p, c)


# ----------------------------------------------------------------------
# 3. SubEditActivity.kt
# ----------------------------------------------------------------------
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/subscription/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found")
        return
    c = read(p)

    old_suggestions = "profileSuggestions = suggestions"
    if old_suggestions in c:
        c = c.replace(old_suggestions, '''profileSuggestions = listOf("None", "[Current Server]") + suggestions''', 1)
        print("✓ SubEditActivity: added special items")

    old_load_prev = 'var prevProfile by rememberSaveable { mutableStateOf(initial.prevProfile ?: "") }'
    new_load_prev = '''    var prevProfile by rememberSaveable { mutableStateOf(
        when (initial.prevProfile) {
            "" -> "None"
            AppConfig.CURRENT_SERVER -> "[Current Server]"
            else -> initial.prevProfile ?: ""
        }
    ) }'''
    if "var prevProfile by rememberSaveable" in c:
        c = c.replace(old_load_prev, new_load_prev, 1)

    old_load_next = 'var nextProfile by rememberSaveable { mutableStateOf(initial.nextProfile ?: "") }'
    new_load_next = '''    var nextProfile by rememberSaveable { mutableStateOf(
        when (initial.nextProfile) {
            "" -> "None"
            AppConfig.CURRENT_SERVER -> "[Current Server]"
            else -> initial.nextProfile ?: ""
        }
    ) }'''
    if "var nextProfile by rememberSaveable" in c:
        c = c.replace(old_load_next, new_load_next, 1)

    old_save_prev = "subItem.prevProfile = prevProfile"
    new_save_prev = '''        subItem.prevProfile = when (prevProfile) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> prevProfile
        }'''
    if old_save_prev in c:
        c = c.replace(old_save_prev, new_save_prev, 1)

    old_save_next = "subItem.nextProfile = nextProfile"
    new_save_next = '''        subItem.nextProfile = when (nextProfile) {
            "None" -> ""
            "[Current Server]" -> AppConfig.CURRENT_SERVER
            else -> nextProfile
        }'''
    if old_save_next in c:
        c = c.replace(old_save_next, new_save_next, 1)

    write(p, c)


# ----------------------------------------------------------------------
# 4. strings.xml
# ----------------------------------------------------------------------
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    c = read(p)

    new_strings = []
    needed = {
        "sub_setting_none": "None",
        "sub_setting_current_server": "[Current Server]",
        "title_pref_dns_parallel_query": "DNS Parallel Query",
        "summary_pref_dns_parallel_query": "Enable parallel queries to all DNS servers for faster resolution",
        "title_pref_dns_serve_stale": "DNS Serve Stale",
        "summary_pref_dns_serve_stale": "Serve stale DNS records while refreshing in background",
    }
    for k, v in needed.items():
        if f'name="{k}"' not in c:
            new_strings.append(f'    <string name="{k}">{v}</string>')

    if new_strings:
        m = re.search(r'(\s*)</resources>', c, re.IGNORECASE)
        if m:
            indent = m.group(1)
            insertion = "\n" + "\n".join(new_strings) + "\n" + indent
            c = c[:m.start()] + insertion + c[m.start():]
            write(p, c)
            print(f"✓ strings.xml: added {len(new_strings)} strings")


# ----------------------------------------------------------------------
# 5. CoreConfigManager.kt – FIXED
# ----------------------------------------------------------------------
def patch_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found")
        return
    backup_kotlin(p)
    c = read(p)

    # FIXED configureDns
    method_start = c.find("private fun configureDns(")
    if method_start != -1:
        open_brace = c.find('{', method_start)
        if open_brace != -1:
            brace_count = 1
            i = open_brace + 1
            while i < len(c) and brace_count > 0:
                if c[i] == '{': brace_count += 1
                elif c[i] == '}': brace_count -= 1
                i += 1
            if brace_count == 0:
                new_configure_dns = '''    private fun configureDns(
        configContext: CoreConfigContext,
        v2rayConfig: V2rayConfig,
        policyGroupBalancerTags: Map<String, String>,
    ) {
        val servers = ArrayList<Any>()
        val remoteDns = SettingsManager.getRemoteDnsServers()
        val domesticDns = SettingsManager.getDomesticDnsServers()

        remoteDns.forEach { servers.add(it) }

        val hosts = buildDnsHostsFromRoutingRules(configContext)
        val cnDomesticDnsTags = buildDnsCnModeFromRoutingRules(configContext, servers, domesticDns)
        val domesticDnsTags = buildDnsFromRoutingRules(
            configContext = configContext,
            servers = servers,
            remoteDns = remoteDns,
            domesticDns = domesticDns
        )
        domesticDnsTags.addAll(cnDomesticDnsTags)

        val dnsBean = V2rayConfig.DnsBean(
            servers = servers,
            hosts = hosts,
            tag = AppConfig.TAG_DNS,
            enableParallelQuery = null
        )

        if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_SERVE_STALE, false) == true) {
            dnsBean.serveStale = true
        }
        if (MmkvManager.decodeSettingsBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false) == true) {
            dnsBean.enableParallelQuery = true
        }

        v2rayConfig.dns = dnsBean

        if (domesticDnsTags.isNotEmpty()) {
            v2rayConfig.routing.rules.add(
                V2rayConfig.RoutingBean.RulesBean(
                    outboundTag = AppConfig.TAG_DIRECT,
                    inboundTag = ArrayList(domesticDnsTags),
                    domain = null
                )
            )
        }

        val dnsProxyBalancerTag = policyGroupBalancerTags[AppConfig.TAG_PROXY]
        if (dnsProxyBalancerTag != null) {
            v2rayConfig.routing.rules.add(
                V2rayConfig.RoutingBean.RulesBean(
                    balancerTag = dnsProxyBalancerTag,
                    inboundTag = arrayListOf(AppConfig.TAG_DNS),
                    domain = null
                )
            )
        } else {
            v2rayConfig.routing.rules.add(
                V2rayConfig.RoutingBean.RulesBean(
                    outboundTag = AppConfig.TAG_PROXY,
                    inboundTag = arrayListOf(AppConfig.TAG_DNS),
                    domain = null
                )
            )
        }
    }'''
                c = c[:method_start] + new_configure_dns + c[i:]
                print("✓ CoreConfigManager: configureDns fixed with DNS prefs")

    write(p, c)


# ----------------------------------------------------------------------
# 6. SettingsActivity.kt
# ----------------------------------------------------------------------
def patch_settings():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/settings/SettingsActivity.kt"
    if not p.exists():
        print("✗ SettingsActivity.kt not found")
        return
    c = read(p)

    old_decls = 'var dnsHosts by rememberMmkvString(AppConfig.PREF_DNS_HOSTS, "")'
    new_decls = old_decls + '''
    var dnsParallelQuery by rememberMmkvBool(AppConfig.PREF_DNS_PARALLEL_QUERY, false)
    var dnsServeStale by rememberMmkvBool(AppConfig.PREF_DNS_SERVE_STALE, false)'''

    if old_decls in c and "dnsParallelQuery" not in c:
        c = c.replace(old_decls, new_decls, 1)
        print("✓ SettingsActivity: DNS states added")

    pattern = r'(SettingsEditItem\(\s*title = stringResource\(R\.string\.title_pref_dns_hosts\),\s*value = dnsHosts,\s*onValueChanged = \{ dnsHosts = it \}\s*\))'
    if re.search(pattern, c, re.DOTALL) and "title_pref_dns_parallel_query" not in c:
        replacement = r'\1\n                SettingsSwitchItem(\n                    title = stringResource(R.string.title_pref_dns_parallel_query),\n                    summary = stringResource(R.string.summary_pref_dns_parallel_query),\n                    checked = dnsParallelQuery,\n                    onCheckedChange = { dnsParallelQuery = it }\n                )\n                SettingsSwitchItem(\n                    title = stringResource(R.string.title_pref_dns_serve_stale),\n                    summary = stringResource(R.string.summary_pref_dns_serve_stale),\n                    checked = dnsServeStale,\n                    onCheckedChange = { dnsServeStale = it }\n                )'
        c = re.sub(pattern, replacement, c, flags=re.DOTALL)
        print("✓ SettingsActivity: DNS switches inserted")

    write(p, c)


# ----------------------------------------------------------------------
# 7. FormFields.kt – Fixed dropdown (LazyColumn inside ExposedDropdownMenu)
# ----------------------------------------------------------------------
def patch_formfields():
    p = BASE / "app/src/main/java/com/v2ray/ang/compose/FormFields.kt"
    if not p.exists():
        print("✗ FormFields.kt not found")
        return
    c = read(p)

    # Add necessary imports
    if "heightIn" not in c:
        last_import = list(re.finditer(r'^import .*', c, re.MULTILINE))[-1]
        pos = last_import.end()
        c = c[:pos] + "\nimport androidx.compose.foundation.layout.heightIn\nimport androidx.compose.foundation.lazy.LazyColumn\nimport androidx.compose.foundation.lazy.items" + c[pos:]
        print("✓ FormFields: added LazyColumn imports")

    # Replace dropdown
    old_menu = re.search(r'ExposedDropdownMenu\(.*?\)\s*\{.*?\}', c, re.DOTALL)
    if old_menu:
        new_menu = '''        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier
                .verticalScrollbar(menuScrollState)
                .heightIn(max = 300.dp),
            scrollState = menuScrollState,
            containerColor = MaterialTheme.colorScheme.surface
        ) {
            LazyColumn(
                modifier = Modifier.heightIn(max = 300.dp),
                state = menuScrollState
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
        c = c.replace(old_menu.group(0), new_menu)
        print("✓ FormFields: LazyColumn dropdown (fast & stable)")

    write(p, c)


# ----------------------------------------------------------------------
def main():
    print("=" * 80)
    print("✅ COMPLETE FIXED PATCHER")
    print("=" * 80)

    patch_appconfig()
    patch_v2rayconfig()
    patch_subedit()
    patch_strings()
    patch_coreconfigmanager()
    patch_settings()
    patch_formfields()

    print("\n✅ All patches applied.")
    print("Run: cd V2rayNG && ./gradlew clean assembleDebug")

if __name__ == "__main__":
    main()

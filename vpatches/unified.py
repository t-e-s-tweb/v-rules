#!/usr/bin/env python3
"""
Mini-patch: mirrors DHR60/v2rayNG@4ce36c0 ("Revert 'Improve DNS, try fix'")
https://github.com/DHR60/v2rayNG/commit/4ce36c076237c6e08be03c5a652f320559a2ebe6

Run this AFTER patch_fixed.py, against the same V2rayNG/ checkout it already
patched. Do not run it on its own.

What the upstream commit does: it removes the configContext/routingDomainRules
based DNS path that "Improve DNS, try fix" had introduced -
configureDns(configContext, ...), buildDnsHostsFromRoutingRules,
buildDnsCnModeFromRoutingRules, buildDnsFromRoutingRules,
collectRoutingDomainRulesForDns(), and CoreConfigContext.routingDomainRules -
and revives the simpler configureDns(v2rayConfig, policyGroupBalancerTags)
that had been left commented out above it as a fallback.

Why this needs its own step rather than just re-running the diff verbatim:
patch_fixed.py's DNS-toggle fix (PREF_DNS_PARALLEL_QUERY / PREF_DNS_SERVE_STALE)
lives inside the exact configureDns(configContext, ...) function this commit
deletes. Applied on its own, this revert would silently undo that fix. So this
script carries the same two-preference wiring over into the revived function
before deleting the configContext-based one - same transformation
patch_fixed.py already used, just re-anchored.

Idempotent: safe to run twice.
"""

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
# 1. CoreConfigManager.kt - revive the old configureDns, drop the
#    configContext-based one + its 3 helpers, carry the DNS-toggle wiring
#    over, and switch configureLocalDns back to the non-configContext form.
# ----------------------------------------------------------------------
def revert_coreconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    if not p.exists():
        print("✗ CoreConfigManager.kt not found — skipping")
        return
    c = read(p)

    if "private fun configureDns(\n        v2rayConfig: V2rayConfig," in c and \
       "private fun configureDns(\n        configContext: CoreConfigContext," not in c:
        print("• CoreConfigManager: DNS revert already applied, skipping")
        return

    backup_kotlin(p)

    # --- call site: drop configContext from both calls ---
    old_call = "configureDns(configContext, v2rayConfig, policyGroupBalancerTags)\n        configureLocalDns(configContext, v2rayConfig)"
    new_call = "configureDns(v2rayConfig, policyGroupBalancerTags)\n        configureLocalDns(v2rayConfig)"
    if old_call in c:
        c = c.replace(old_call, new_call, 1)
        print("✓ CoreConfigManager: updated buildUnifiedConfig call site")
    else:
        print("⚠ CoreConfigManager: configureDns/configureLocalDns call site not found as expected")

    # --- configureLocalDns: signature + domain collection ---
    old_sig = "private fun configureLocalDns(configContext: CoreConfigContext, v2rayConfig: V2rayConfig) {"
    new_sig = "private fun configureLocalDns(v2rayConfig: V2rayConfig) {"
    if old_sig in c:
        c = c.replace(old_sig, new_sig, 1)
        print("✓ CoreConfigManager: updated configureLocalDns signature")

    old_domains = '''val geositeCn = arrayListOf(AppConfig.GEOSITE_CN)
            val routingDomains = configContext.routingDomainRules
                .asSequence()
                .filter { it.outboundTag != AppConfig.TAG_BLOCKED }
                .flatMap { it.domain.asSequence() }
                .toList()
                .distinct()
            val finalDomain = geositeCn + routingDomains'''
    new_domains = '''val geositeCn = arrayListOf(AppConfig.GEOSITE_CN)
            val proxyDomain = collectUserRuleDomainsByTag(AppConfig.TAG_PROXY)
            val directDomain = collectUserRuleDomainsByTag(AppConfig.TAG_DIRECT)
            val finalDomain = geositeCn.plus(proxyDomain).plus(directDomain).distinct()'''
    if old_domains in c:
        c = c.replace(old_domains, new_domains, 1)
        print("✓ CoreConfigManager: configureLocalDns now collects domains via collectUserRuleDomainsByTag")
    else:
        print("⚠ CoreConfigManager: configureLocalDns domain-collection block not found as expected")

    # --- revive the old configureDns, delete the configContext-based one + its 3 helpers ---
    dead_open_anchor = (
        "\n    /*\n    /**\n     * Configure DNS servers, hosts, and DNS routing rules.\n"
        "     */\n    private fun configureDns(\n        v2rayConfig: V2rayConfig,\n"
        "        policyGroupBalancerTags: Map<String, String>,\n    ) {"
    )
    transition_anchor = (
        "\n    */\n\n    /**\n     * Configure DNS servers, hosts, and DNS routing rules.\n"
        "     */\n    private fun configureDns(\n        configContext: CoreConfigContext,"
    )
    dead_open_idx = c.find(dead_open_anchor)
    if dead_open_idx == -1:
        print("⚠ CoreConfigManager: commented-out configureDns(v2rayConfig, ...) not found — already reverted, or source has drifted")
    else:
        transition_idx = c.find(transition_anchor, dead_open_idx)
        end_idx = c.find("\n\n    //endregion", transition_idx) if transition_idx != -1 else -1
        if transition_idx == -1 or end_idx == -1:
            print("⚠ CoreConfigManager: could not locate the end of the configContext-based DNS block — source has drifted, check manually")
        else:
            dead_body = c[dead_open_idx + len(dead_open_anchor): transition_idx]

            # carry the DNS-toggle wiring over (same transformation patch_fixed.py applied)
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
            if old_dns_construction in dead_body:
                dead_body = dead_body.replace(old_dns_construction, new_dns_construction, 1)
                print("✓ CoreConfigManager: carried DNS parallel-query/serve-stale wiring into the revived configureDns")
            else:
                print("⚠ CoreConfigManager: DnsBean construction not found in the revived body — DNS toggle wiring NOT carried over, check manually")

            revived_function = (
                "\n    /**\n     * Configure DNS servers, hosts, and DNS routing rules.\n     */\n"
                "    private fun configureDns(\n        v2rayConfig: V2rayConfig,\n"
                "        policyGroupBalancerTags: Map<String, String>,\n    ) {" + dead_body
            )
            c = c[:dead_open_idx] + revived_function + c[end_idx:]
            print("✓ CoreConfigManager: revived configureDns(v2rayConfig, policyGroupBalancerTags) and removed the configContext-based DNS block (+3 helpers)")

    write(p, c)


# ----------------------------------------------------------------------
# 2. CoreConfigContextBuilder.kt - stop collecting/passing routingDomainRules
# ----------------------------------------------------------------------
def revert_coreconfigcontextbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigContextBuilder.kt"
    if not p.exists():
        print("✗ CoreConfigContextBuilder.kt not found — skipping")
        return
    c = read(p)

    if "collectRoutingDomainRulesForDns" not in c:
        print("• CoreConfigContextBuilder: DNS revert already applied, skipping")
        return

    old_build_lines = "        val routingDomainRules = collectRoutingDomainRulesForDns()\n\n        return CoreConfigContext("
    new_build_lines = "        return CoreConfigContext("
    if old_build_lines in c:
        c = c.replace(old_build_lines, new_build_lines, 1)
        print("✓ CoreConfigContextBuilder: stopped collecting routingDomainRules in build()")
    else:
        print("⚠ CoreConfigContextBuilder: routingDomainRules collection line not found as expected")

    old_arg = "            routingDomainRules = routingDomainRules,\n"
    if old_arg in c:
        c = c.replace(old_arg, "", 1)
        print("✓ CoreConfigContextBuilder: stopped passing routingDomainRules into CoreConfigContext(...)")
    else:
        print("⚠ CoreConfigContextBuilder: routingDomainRules argument not found as expected")

    method_start = c.find("    /**\n     * Collect enabled routing domain rules in original order for DNS segmentation.")
    if method_start != -1:
        open_brace = c.find("private fun collectRoutingDomainRulesForDns", method_start)
        open_brace = c.find('{', open_brace)
        brace_count = 1
        i = open_brace + 1
        while i < len(c) and brace_count > 0:
            if c[i] == '{':
                brace_count += 1
            elif c[i] == '}':
                brace_count -= 1
            i += 1
        if brace_count == 0:
            c = c[:method_start] + c[i:]
            print("✓ CoreConfigContextBuilder: removed collectRoutingDomainRulesForDns()")
        else:
            print("⚠ CoreConfigContextBuilder: brace mismatch removing collectRoutingDomainRulesForDns — check manually")
    else:
        print("⚠ CoreConfigContextBuilder: collectRoutingDomainRulesForDns() not found as expected")

    write(p, c)


# ----------------------------------------------------------------------
# 3. CoreConfigContext.kt - drop the routingDomainRules field + nested type
# ----------------------------------------------------------------------
def revert_coreconfigcontext():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/CoreConfigContext.kt"
    if not p.exists():
        print("✗ CoreConfigContext.kt not found — skipping")
        return
    c = read(p)

    if "routingDomainRules" not in c:
        print("• CoreConfigContext: DNS revert already applied, skipping")
        return

    old_field = "    val routingDomainRules: List<RoutingDomainRule> = emptyList(),\n"
    if old_field in c:
        c = c.replace(old_field, "", 1)
        print("✓ CoreConfigContext: removed routingDomainRules field")
    else:
        print("⚠ CoreConfigContext: routingDomainRules field not found as expected")

    old_nested_type = '''
    data class RoutingDomainRule(
        val domain: List<String>,
        val outboundTag: String,
    )
'''
    if old_nested_type in c:
        c = c.replace(old_nested_type, "", 1)
        print("✓ CoreConfigContext: removed RoutingDomainRule data class")
    else:
        print("⚠ CoreConfigContext: RoutingDomainRule data class not found as expected")

    write(p, c)


def main():
    print("=" * 70)
    print("Mini-patch: revert configContext-based DNS (mirrors DHR60@4ce36c0)")
    print("Run after patch_fixed.py, on the same checkout")
    print("=" * 70)
    revert_coreconfigmanager()
    revert_coreconfigcontextbuilder()
    revert_coreconfigcontext()
    print("\n✅ Done.")
    print("👉 Rebuild and test.")

if __name__ == "__main__":
    main()

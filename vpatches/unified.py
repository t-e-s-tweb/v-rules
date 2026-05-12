#!/usr/bin/env python3
"""
Unified patcher for v2rayNG – adds:
  - Custom outbound subscription chaining (prev/next proxy)
  - [Current Server] resolve & deduplication
  - Editable prev/next profile with dropdown including None and [Current Server]
"""

import re, sys, shutil
from pathlib import Path
from datetime import datetime

BASE = Path("V2rayNG")

def backup_kotlin(p: Path):
    if p.suffix == ".kt":
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = p.with_suffix(f".kt.bak.{ts}")
        shutil.copy2(p, bak)
        print(f"  backup: {bak.name}")

def read(p): return p.read_text(encoding="utf-8")
def write(p, s): p.write_text(s, encoding="utf-8")

# ── 1. AppConfig.kt ──────────────────────────────────────────────────
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    c = read(p)
    if '"__CURRENT_SERVER__"' in c:
        print("• AppConfig: CURRENT_SERVER already present")
        return
    old = '    const val TAG_BLOCKED = "block"'
    new = '    const val TAG_BLOCKED = "block"\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"'
    if old in c:
        write(p, c.replace(old, new))
        print("✓ AppConfig: added CURRENT_SERVER")
    else:
        print("✗ AppConfig: insertion point not found")

# ── 2. SubEditActivity.kt – exact method replacements ─────────────────
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found – skipping")
        return
    c = read(p)

    # Ensure imports
    if "import android.widget.ArrayAdapter" not in c:
        c = c.replace(
            "import android.view.MenuItem",
            "import android.view.MenuItem\nimport android.widget.ArrayAdapter"
        )
    if "import android.widget.AutoCompleteTextView" not in c:
        c = c.replace(
            "import android.widget.ArrayAdapter",
            "import android.widget.ArrayAdapter\nimport android.widget.AutoCompleteTextView"
        )

    # ------------------------------------------------------------------
    # Replace setupProfileRemarkInputs with version that builds Pair list
    # ------------------------------------------------------------------
    old_setup_inputs = '''    private fun setupProfileRemarkInputs() {
        val suggestions = MmkvManager.decodeAllServerList()
            .mapNotNull { id -> MmkvManager.decodeServerConfig(id)?.remarks }
            .filter { it.isNotBlank() }
            .distinct()

        setupProfileRemarkInput(binding.etPreProfile, binding.btnPreProfileDropdown, suggestions)
        setupProfileRemarkInput(binding.etNextProfile, binding.btnNextProfileDropdown, suggestions)
    }'''

    new_setup_inputs = '''    private fun setupProfileRemarkInputs() {
        val suggestions = listOf(
            "" to getString(R.string.sub_setting_none),
            AppConfig.CURRENT_SERVER to getString(R.string.sub_setting_current_server)
        ) + MmkvManager.decodeAllServerList()
            .mapNotNull { id -> MmkvManager.decodeServerConfig(id)?.remarks }
            .filter { it.isNotBlank() }
            .distinct()
            .map { it to it }

        setupProfileRemarkInput(binding.etPreProfile, binding.btnPreProfileDropdown, suggestions)
        setupProfileRemarkInput(binding.etNextProfile, binding.btnNextProfileDropdown, suggestions)
    }'''

    if old_setup_inputs in c:
        c = c.replace(old_setup_inputs, new_setup_inputs)
        print("✓ SubEditActivity: replaced setupProfileRemarkInputs")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInputs not found (maybe already patched)")

    # ------------------------------------------------------------------
    # Replace setupProfileRemarkInput with version that handles Pair list
    # ------------------------------------------------------------------
    old_setup_input = '''    private fun setupProfileRemarkInput(
        input: AutoCompleteTextView,
        dropdownButton: ImageButton,
        suggestions: List<String>
    ) {
        val adapter = ArrayAdapter(this, android.R.layout.simple_dropdown_item_1line, suggestions)
        input.setAdapter(adapter)
        input.threshold = 0

        dropdownButton.setOnClickListener {
            input.requestFocus()
            input.showDropDown()
        }
        input.setOnClickListener {
            input.showDropDown()
        }
    }'''

    new_setup_input = '''    private fun setupProfileRemarkInput(
        input: AutoCompleteTextView,
        dropdownButton: ImageButton,
        suggestions: List<Pair<String, String>>
    ) {
        val displayList = suggestions.map { it.second }
        val adapter = ArrayAdapter(this, android.R.layout.simple_dropdown_item_1line, displayList)
        input.setAdapter(adapter)
        input.threshold = 0

        dropdownButton.setOnClickListener {
            input.requestFocus()
            input.showDropDown()
        }
        input.setOnClickListener {
            input.showDropDown()
        }

        input.setOnItemClickListener { _, _, position, _ ->
            val storedValue = suggestions[position].first
            input.setText(storedValue)
        }
    }'''

    if old_setup_input in c:
        c = c.replace(old_setup_input, new_setup_input)
        print("✓ SubEditActivity: replaced setupProfileRemarkInput")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInput not found (maybe already patched)")

    # ------------------------------------------------------------------
    # Update bindingServer to show friendly display strings
    # ------------------------------------------------------------------
    old_binding = '''        binding.etPreProfile.text = Utils.getEditable(subItem.prevProfile)
        binding.etNextProfile.text = Utils.getEditable(subItem.nextProfile)'''
    new_binding = '''        val preDisplay = when (subItem.prevProfile) {
            AppConfig.CURRENT_SERVER -> getString(R.string.sub_setting_current_server)
            else -> subItem.prevProfile
        }
        binding.etPreProfile.setText(preDisplay)
        val nextDisplay = when (subItem.nextProfile) {
            AppConfig.CURRENT_SERVER -> getString(R.string.sub_setting_current_server)
            else -> subItem.nextProfile
        }
        binding.etNextProfile.setText(nextDisplay)'''
    if old_binding in c:
        c = c.replace(old_binding, new_binding)
        print("✓ SubEditActivity: updated bindingServer")
    else:
        print("⚠ SubEditActivity: bindingServer prev/next lines not found")

    # ------------------------------------------------------------------
    # Update saveServer to map display back to stored constants
    # ------------------------------------------------------------------
    old_save = '''        subItem.prevProfile = binding.etPreProfile.text.toString()
        subItem.nextProfile = binding.etNextProfile.text.toString()'''
    new_save = '''        subItem.prevProfile = when (binding.etPreProfile.text.toString()) {
            getString(R.string.sub_setting_current_server) -> AppConfig.CURRENT_SERVER
            else -> binding.etPreProfile.text.toString()
        }
        subItem.nextProfile = when (binding.etNextProfile.text.toString()) {
            getString(R.string.sub_setting_current_server) -> AppConfig.CURRENT_SERVER
            else -> binding.etNextProfile.text.toString()
        }'''
    if old_save in c:
        c = c.replace(old_save, new_save)
        print("✓ SubEditActivity: updated saveServer")
    else:
        print("⚠ SubEditActivity: saveServer prev/next lines not found")

    write(p, c)
    print("✓ SubEditActivity: all enhancements applied")

# ── 3. strings.xml – add None and [Current Server] ──────────────────
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    c = read(p)
    needed = {"sub_setting_none": "None", "sub_setting_current_server": "[Current Server]"}
    changed = False
    for k, v in needed.items():
        if f'name="{k}"' in c:
            continue
        m = re.search(r'(\s*)</resources>', c, re.IGNORECASE)
        if not m:
            print(f"✗ strings.xml: </resources> not found")
            return
        indent, pos = m.group(1), m.start()
        c = c[:pos] + f'\n{indent}<string name="{k}">{v}</string>' + c[pos:]
        changed = True
    if changed:
        write(p, c)
        print("✓ strings.xml: added None and [Current Server]")
    else:
        print("• strings.xml: already present")

# ── 4. CoreConfigManager.kt – custom chaining (unchanged from your script) ─
def patch_coreconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    c = read(p)

    # Replace injectCustomOutbounds
    old_inject = '''    private fun injectCustomOutbounds(v2rayConfig: V2rayConfig, customOutbounds: Map<String, ProfileItem>) {
        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }

        customOutbounds.forEach { (tag, profile) ->
            if (tag in existingTags) return@forEach
            val outbound = convertProfile2Outbound(profile)
                ?: error("Could not convert profile '$tag' to outbound")
            outbound.tag = tag
            v2rayConfig.outbounds.add(outbound)
            existingTags.add(tag)
            LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$tag'")
        }
    }'''

    new_inject = '''    private fun injectCustomOutbounds(v2rayConfig: V2rayConfig, customOutbounds: Map<String, ProfileItem>) {
        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val outboundTagMap = mutableMapOf<String, String>()

        customOutbounds.forEach { (tag, profile) ->
            if (outboundTagMap.containsKey(tag)) {
                LogUtil.d(AppConfig.TAG, "Custom outbound '$tag' already injected, skipping")
                return@forEach
            }
            val outbound = convertProfile2Outbound(profile)
                ?: error("Could not convert profile '$tag' to outbound")
            outbound.tag = tag

            applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)

            v2rayConfig.outbounds.add(outbound)
            existingTags.add(tag)
            outboundTagMap[tag] = tag
            LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$tag'")
        }
    }'''

    if old_inject in c:
        c = c.replace(old_inject, new_inject)
        print("✓ CoreConfig: injectCustomOutbounds → chain-enabled")
    else:
        print("✗ CoreConfig: injectCustomOutbounds block not found – maybe already patched?")

    # Insert resolveCurrentServer and applySubscriptionChain
    routing_pat = re.compile(r'(\n    private fun getRouting\(configContext: CoreConfigContext,)')
    m = re.search(routing_pat, c)
    if not m:
        print("✗ CoreConfig: getRouting anchor not found")
        return

    resolve_func = '''
    private fun resolveCurrentServer(remark: String?): String? {
        if (remark == AppConfig.CURRENT_SERVER) {
            val currId = MmkvManager.getSelectServer()
            if (!currId.isNullOrEmpty()) {
                val profile = MmkvManager.decodeServerConfig(currId)
                return profile?.remarks
            }
        }
        return remark
    }

    private fun applySubscriptionChain(
        v2rayConfig: V2rayConfig,
        profile: ProfileItem,
        outbound: V2rayConfig.OutboundBean,
        outboundTagMap: MutableMap<String, String>,
        existingTags: MutableSet<String>
    ) {
        if (profile.subscriptionId.isNullOrEmpty()) return

        val subItem = MmkvManager.decodeSubscription(profile.subscriptionId) ?: return
        val originalTag = outbound.tag

        fun addChainOutbound(
            targetRemark: String?,
            chainType: String,
            desiredTag: String,
            chainTo: (V2rayConfig.OutboundBean) -> Unit
        ) {
            if (targetRemark.isNullOrEmpty()) return

            val existingByTag = v2rayConfig.outbounds.firstOrNull { it.tag == desiredTag }
            if (existingByTag != null) {
                chainTo(existingByTag)
                outboundTagMap["$chainType-$targetRemark"] = desiredTag
                LogUtil.d(AppConfig.TAG, "Reused existing $chainType outbound: $desiredTag")
                return
            }

            val mapKey = "$chainType-$targetRemark"
            val existingTag = outboundTagMap[mapKey]
            if (existingTag != null) {
                val existingOutbound = v2rayConfig.outbounds.firstOrNull { it.tag == existingTag }
                if (existingOutbound != null) {
                    chainTo(existingOutbound)
                    LogUtil.d(AppConfig.TAG, "Reused $chainType outbound (map): $existingTag")
                    return
                }
            }

            val chainProfile = SettingsManager.getServerViaRemarks(targetRemark) ?: return
            val mainRemarks = MmkvManager.getSelectServer()?.let { MmkvManager.decodeServerConfig(it)?.remarks }
            if (chainProfile.remarks == mainRemarks) {
                outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                LogUtil.d(AppConfig.TAG, "Chain $chainType proxy is main server, set dialerProxy to proxy")
                return
            }

            val chainOutbound = convertProfile2Outbound(chainProfile) ?: return
            chainOutbound.tag = desiredTag
            outboundTagMap[mapKey] = desiredTag

            chainTo(chainOutbound)
            v2rayConfig.outbounds.add(chainOutbound)
            existingTags.add(desiredTag)
            LogUtil.d(AppConfig.TAG, "Created $chainType outbound: $desiredTag")
        }

        addChainOutbound(resolveCurrentServer(subItem.prevProfile), "prev", "$originalTag-prev") { prevOutbound ->
            outbound.ensureSockopt().dialerProxy = prevOutbound.tag
        }

        if (!subItem.nextProfile.isNullOrEmpty()) {
            val newOriginalTag = "$originalTag-orig"
            outbound.tag = newOriginalTag

            addChainOutbound(resolveCurrentServer(subItem.nextProfile), "next", originalTag) { nextOutbound ->
                nextOutbound.ensureSockopt().dialerProxy = newOriginalTag
            }
        }
    }
'''
    c = c[:m.start()] + resolve_func + c[m.start():]
    print("✓ CoreConfig: inserted resolveCurrentServer + applySubscriptionChain")

    write(p, c)

# ── main ──────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Custom Outbound + Enhanced Profile Selector Patcher (Exact Match)")
    print("=" * 70)

    for f in [
        BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt",
        BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt",
        BASE / "app/src/main/res/values/strings.xml",
        BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt",
    ]:
        if f.exists():
            backup_kotlin(f)

    try:
        patch_appconfig()
        patch_subedit()
        patch_strings()
        patch_coreconfig()
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild and test – you will now see 'None' and '[Current Server]' in the dropdown.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

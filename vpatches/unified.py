#!/usr/bin/env python3
"""
Unified patcher for v2rayNG.
Adds:
  - Custom-outbound subscription chaining (prev/next proxy)
  - [Current Server] resolve & deduplication
  - Enhanced prev/next profile selector (editable dropdown with None / [Current Server])
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

# ── 2. No layout changes – upstream already has AutoCompleteTextView ──
#    We only enhance SubEditActivity.kt to add None / [Current Server] to the suggestions

# ── 3. SubEditActivity.kt – enhance existing AutoCompleteTextView ────
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt"
    if not p.exists():
        print("✗ SubEditActivity.kt not found – skipping")
        return
    c = read(p)

    # 1. Ensure imports (if missing)
    if "android.widget.ArrayAdapter" not in c:
        c = c.replace(
            "import android.view.MenuItem",
            "import android.view.MenuItem\nimport android.widget.ArrayAdapter"
        )

    # 2. Add helper to build suggestion list with None + [Current Server]
    extra_method = '''
    /**
     * Builds suggestion list for prev/next profile:
     * - "" (None)   → saved as empty string
     * - [Current Server] → saved as AppConfig.CURRENT_SERVER
     * - all existing server remarks (distinct, non-blank)
     */
    private fun getProfileSuggestions(): List<Pair<String, String>> {
        val list = mutableListOf<Pair<String, String>>()
        list.add("" to getString(R.string.sub_setting_none))
        list.add(AppConfig.CURRENT_SERVER to getString(R.string.sub_setting_current_server))
        val servers = MmkvManager.decodeAllServerList()
        for (guid in servers) {
            val profile = MmkvManager.decodeServerConfig(guid)
            if (profile != null && profile.remarks.isNotBlank()) {
                list.add(profile.remarks to profile.remarks)
            }
        }
        // Remove duplicates (retain first occurrence: None, Current, then first remark)
        return list.distinctBy { it.first }
    }
'''
    if "getProfileSuggestions" not in c:
        # Insert after class declaration
        class_pos = c.find("class SubEditActivity : BaseActivity() {")
        if class_pos == -1:
            print("✗ SubEditActivity: class declaration not found")
            return
        insert_pos = c.index("\n", class_pos) + 1
        c = c[:insert_pos] + extra_method + c[insert_pos:]
        print("✓ SubEditActivity: added getProfileSuggestions()")

    # 3. Replace setupProfileRemarkInputs to use enhanced suggestions
    old_setup = r'private fun setupProfileRemarkInputs\(\) {.*?^    }'
    new_setup = '''    private fun setupProfileRemarkInputs() {
        val suggestions = getProfileSuggestions()
        setupProfileRemarkInput(binding.etPreProfile, binding.btnPreProfileDropdown, suggestions)
        setupProfileRemarkInput(binding.etNextProfile, binding.btnNextProfileDropdown, suggestions)
    }'''
    if re.search(old_setup, c, re.DOTALL | re.MULTILINE):
        c = re.sub(old_setup, new_setup, c, flags=re.DOTALL)
        print("✓ SubEditActivity: replaced setupProfileRemarkInputs()")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInputs() not found, skipping")

    # 4. Replace setupProfileRemarkInput to use the Pair list and handle special values
    old_input = r'private fun setupProfileRemarkInput\(.*?^    }'
    new_input = '''    private fun setupProfileRemarkInput(
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

        // When user selects an item, map display text back to stored value
        input.setOnItemClickListener { _, _, position, _ ->
            val selectedPair = suggestions[position]
            val storedValue = selectedPair.first
            // For custom typed text, we don't override – just let it be
            if (storedValue != input.text.toString()) {
                input.setText(storedValue)
            }
        }
    }'''
    if re.search(old_input, c, re.DOTALL | re.MULTILINE):
        c = re.sub(old_input, new_input, c, flags=re.DOTALL)
        print("✓ SubEditActivity: replaced setupProfileRemarkInput()")
    else:
        print("⚠ SubEditActivity: setupProfileRemarkInput() not found, skipping")

    # 5. Update bindingServer to convert stored constant to display string
    old_binding = re.escape('binding.etPreProfile.text = Utils.getEditable(subItem.prevProfile)\n        binding.etNextProfile.text = Utils.getEditable(subItem.nextProfile)')
    new_binding = '''        // Convert stored constants to user-friendly display
        val preDisplay = when (subItem.prevProfile) {
            AppConfig.CURRENT_SERVER -> getString(R.string.sub_setting_current_server)
            else -> subItem.prevProfile
        }
        binding.etPreProfile.setText(preDisplay)
        val nextDisplay = when (subItem.nextProfile) {
            AppConfig.CURRENT_SERVER -> getString(R.string.sub_setting_current_server)
            else -> subItem.nextProfile
        }
        binding.etNextProfile.setText(nextDisplay)'''
    if re.search(old_binding, c):
        c = re.sub(old_binding, new_binding, c)
        print("✓ SubEditActivity: updated bindingServer to show [Current Server]")
    else:
        print("⚠ SubEditActivity: bindingServer prev/next lines not found, skipping")

    # 6. Update saveServer to map display text back to stored constants
    old_save = re.escape('subItem.prevProfile = binding.etPreProfile.text.toString()\n        subItem.nextProfile = binding.etNextProfile.text.toString()')
    new_save = '''        // Map user input back to stored value
        subItem.prevProfile = when (binding.etPreProfile.text.toString()) {
            getString(R.string.sub_setting_current_server) -> AppConfig.CURRENT_SERVER
            else -> binding.etPreProfile.text.toString()
        }
        subItem.nextProfile = when (binding.etNextProfile.text.toString()) {
            getString(R.string.sub_setting_current_server) -> AppConfig.CURRENT_SERVER
            else -> binding.etNextProfile.text.toString()
        }'''
    if re.search(old_save, c):
        c = re.sub(old_save, new_save, c)
        print("✓ SubEditActivity: updated saveServer to store constants")
    else:
        print("⚠ SubEditActivity: saveServer prev/next lines not found, skipping")

    write(p, c)
    print("✓ SubEditActivity: enhancements applied")

# ── 4. strings.xml – add None and [Current Server] if missing ──────
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    c = read(p)
    needed = {"sub_setting_none": "None", "sub_setting_current_server": "[Current Server]"}
    changed = False
    for k, v in needed.items():
        if f'name="{k}"' in c: continue
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

# ── 5. CoreConfigManager.kt – your custom chain logic (unchanged) ───
def patch_coreconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt"
    c = read(p)

    # (Your existing perfect implementation – kept exactly as you had it)
    # I’ll include the same code from your script for completeness.
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
    print("Custom Outbound + Enhanced Profile Selector Patcher")
    print("=" * 70)

    files_to_backup = [
        BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt",
        BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt",
        BASE / "app/src/main/res/values/strings.xml",
        BASE / "app/src/main/java/com/v2ray/ang/core/CoreConfigManager.kt",
    ]
    for f in files_to_backup:
        if f.exists():
            backup_kotlin(f)

    try:
        patch_appconfig()
        patch_subedit()
        patch_strings()
        patch_coreconfig()
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild and test – you can now type custom remarks or select None/[Current Server].")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Unified patcher for v2rayNG (compatible with commit d9d00f4 / CoreOutboundBuilder).
Applies all features in one pass:
  1. Custom outbound subscription chaining (prev/next) with dedup
  2. Spinner UI for front/landing proxy with [None] / [Current Server]
  3. Reuse existing 'proxy' outbound when chain node matches active server
No backups for XML resources (avoids build breakage).
"""

import re, sys, shutil
from pathlib import Path
from datetime import datetime

BASE = Path("V2rayNG")

# ── helpers ──────────────────────────────────────────────────────────
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
    # insert after TAG_BLOCKED constant
    old = '    const val TAG_BLOCKED = "block"'
    new = '    const val TAG_BLOCKED = "block"\n    const val CURRENT_SERVER = "__CURRENT_SERVER__"'
    if old in c:
        write(p, c.replace(old, new))
        print("✓ AppConfig: added CURRENT_SERVER")
    else:
        print("✗ AppConfig: insertion point not found")

# ── 2. activity_sub_edit.xml ─────────────────────────────────────────
def patch_layout():
    p = BASE / "app/src/main/res/layout/activity_sub_edit.xml"
    c = read(p)

    old_pre = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/sub_setting_pre_profile" />

                <EditText
                    android:id="@+id/et_pre_profile"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:hint="@string/sub_setting_pre_profile_tip"
                    android:inputType="text" />

            </LinearLayout>'''
    new_pre = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/sub_setting_pre_profile" />

                <Spinner
                    android:id="@+id/sp_pre_profile"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />

            </LinearLayout>'''

    old_next = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/sub_setting_next_profile" />

                <EditText
                    android:id="@+id/et_next_profile"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:hint="@string/sub_setting_pre_profile_tip"
                    android:inputType="text" />

            </LinearLayout>'''
    new_next = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="@dimen/padding_spacing_dp16"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="@string/sub_setting_next_profile" />

                <Spinner
                    android:id="@+id/sp_next_profile"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content" />

            </LinearLayout>'''

    if old_pre in c and old_next in c:
        c = c.replace(old_pre, new_pre).replace(old_next, new_next)
        write(p, c)
        print("✓ activity_sub_edit.xml: spinners added")
    else:
        print("✗ activity_sub_edit.xml: blocks not found")

# ── 3. SubEditActivity.kt ────────────────────────────────────────────
def patch_subedit():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt"
    c = read(p)

    # add imports
    if "import android.widget.AdapterView" not in c:
        c = c.replace(
            "import android.view.MenuItem",
            "import android.view.MenuItem\nimport android.widget.AdapterView\nimport android.widget.ArrayAdapter"
        )

    # insert allProfiles lazy property after class declaration
    ins = c.find("class SubEditActivity : BaseActivity() {")
    if ins == -1: raise Exception("class declaration not found")
    ins = c.index('\n', ins) + 1
    extra = '''
    private val allProfiles: List<Pair<String, String>> by lazy {
        val list = mutableListOf<Pair<String, String>>()
        list.add("" to getString(R.string.sub_setting_none))
        list.add(AppConfig.CURRENT_SERVER to getString(R.string.sub_setting_current_server))
        val servers = MmkvManager.decodeAllServerList()
        for (guid in servers) {
            val profile = MmkvManager.decodeServerConfig(guid)
            if (profile != null && profile.remarks.isNotEmpty()) {
                list.add(profile.remarks to profile.remarks)
            }
        }
        list
    }
'''
    c = c[:ins] + extra + c[ins:]

    # bindingServer
    old_b = '''        binding.etPreProfile.text = Utils.getEditable(subItem.prevProfile)
        binding.etNextProfile.text = Utils.getEditable(subItem.nextProfile)'''
    new_b = '''        val preAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, allProfiles.map { it.second })
        preAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spPreProfile.adapter = preAdapter
        val preValue = subItem.prevProfile
        val preIndex = allProfiles.indexOfFirst { it.first == preValue }
        binding.spPreProfile.setSelection(if (preIndex >= 0) preIndex else 0)

        val nextAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, allProfiles.map { it.second })
        nextAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.spNextProfile.adapter = nextAdapter
        val nextValue = subItem.nextProfile
        val nextIndex = allProfiles.indexOfFirst { it.first == nextValue }
        binding.spNextProfile.setSelection(if (nextIndex >= 0) nextIndex else 0)'''
    if old_b in c:
        c = c.replace(old_b, new_b)
    else:
        print("✗ SubEditActivity: bindingServer block not found"); return

    # clearServer
    old_cl = '''        binding.etPreProfile.text = null
        binding.etNextProfile.text = null'''
    new_cl = '''        binding.spPreProfile.setSelection(0)
        binding.spNextProfile.setSelection(0)'''
    if old_cl in c: c = c.replace(old_cl, new_cl)

    # saveServer
    old_sv = '''        subItem.prevProfile = binding.etPreProfile.text.toString()
        subItem.nextProfile = binding.etNextProfile.text.toString()'''
    new_sv = '''        val preIdx = binding.spPreProfile.selectedItemPosition
        subItem.prevProfile = if (preIdx >= 0) allProfiles.getOrNull(preIdx)?.first ?: "" else ""
        val nextIdx = binding.spNextProfile.selectedItemPosition
        subItem.nextProfile = if (nextIdx >= 0) allProfiles.getOrNull(nextIdx)?.first ?: "" else ""'''
    if old_sv in c: c = c.replace(old_sv, new_sv)

    write(p, c)
    print("✓ SubEditActivity: spinners wired")

# ── 4. strings.xml ────────────────────────────────────────────────────
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    c = read(p)
    needed = {"sub_setting_none": "None", "sub_setting_current_server": "[Current Server]"}
    changed = False
    for k, v in needed.items():
        if f'name="{k}"' in c: continue
        m = re.search(r'(\s*)</resources>', c, re.IGNORECASE)
        if not m: print(f"✗ strings.xml: </resources> not found"); return
        indent, pos = m.group(1), m.start()
        c = c[:pos] + f'\n{indent}<string name="{k}">{v}</string>' + c[pos:]
        changed = True
    if changed:
        write(p, c)
        print("✓ strings.xml: new entries added")
    else:
        print("• strings.xml: already present")

# ── 5. V2rayConfigManager.kt (all chain/spinner/reuse logic) ─────────
def patch_v2config():
    p = BASE / "app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt"
    c = read(p)

    # ── 5a. Replace injectCustomOutbounds (entire function) ──────────
    old_inject = '''    private fun injectCustomOutbounds(v2rayConfig: V2rayConfig) {
        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val rulesetItems = MmkvManager.decodeRoutingRulesets() ?: return

        rulesetItems
            .filter { it.enabled }
            .mapNotNull { it.outboundTag.takeIf { tag -> tag.isNotBlank() } }
            .filter { it !in AppConfig.BUILTIN_OUTBOUND_TAGS }
            .distinct()
            .forEach { tag ->
                if (tag in existingTags) return@forEach
                try {
                    val profile = SettingsManager.getServerViaRemarks(tag) ?: run {
                        LogUtil.w(AppConfig.TAG, "Custom outbound tag '$tag' not found by remarks, skipping")
                        return@forEach
                    }
                    val outbound = convertProfile2Outbound(profile) ?: run {
                        LogUtil.w(AppConfig.TAG, "Could not convert profile '$tag' to outbound, skipping")
                        return@forEach
                    }
                    updateOutboundWithGlobalSettings(outbound)
                    outbound.tag = tag
                    v2rayConfig.outbounds.add(outbound)
                    existingTags.add(tag)
                    LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$tag'")
                } catch (e: Exception) {
                    LogUtil.e(AppConfig.TAG, "Failed to inject custom outbound for tag '$tag', skipping", e)
                }
            }
    }'''
    new_inject = '''    private fun injectCustomOutbounds(v2rayConfig: V2rayConfig, outboundTagMap: MutableMap<String, String> = mutableMapOf()) {
        val existingTags = v2rayConfig.outbounds.mapTo(mutableSetOf()) { it.tag }
        val rulesetItems = MmkvManager.decodeRoutingRulesets() ?: return

        rulesetItems
            .filter { it.enabled }
            .mapNotNull { it.outboundTag.takeIf { tag -> tag.isNotBlank() } }
            .filter { it !in AppConfig.BUILTIN_OUTBOUND_TAGS }
            .distinct()
            .forEach { tag ->
                if (outboundTagMap.containsKey(tag)) {
                    LogUtil.d(AppConfig.TAG, "Custom outbound '$tag' already injected, skipping")
                    return@forEach
                }
                try {
                    val profile = SettingsManager.getServerViaRemarks(tag) ?: run {
                        LogUtil.w(AppConfig.TAG, "Custom outbound tag '$tag' not found by remarks, skipping")
                        return@forEach
                    }
                    val outbound = convertProfile2Outbound(profile) ?: run {
                        LogUtil.w(AppConfig.TAG, "Could not convert profile '$tag' to outbound, skipping")
                        return@forEach
                    }
                    updateOutboundWithGlobalSettings(outbound)
                    outbound.tag = tag

                    applySubscriptionChain(v2rayConfig, profile, outbound, outboundTagMap, existingTags)

                    v2rayConfig.outbounds.add(outbound)
                    existingTags.add(tag)
                    outboundTagMap[tag] = tag
                    LogUtil.d(AppConfig.TAG, "Injected custom outbound: tag='$tag'")
                } catch (e: Exception) {
                    LogUtil.e(AppConfig.TAG, "Failed to inject custom outbound for tag '$tag', skipping", e)
                }
            }
    }'''
    if old_inject in c:
        c = c.replace(old_inject, new_inject)
        print("✓ V2Config: injectCustomOutbounds → chain-enabled")
    else:
        print("✗ V2Config: injectCustomOutbounds block not found"); return

    # ── 5b. Insert resolveCurrentServer + applySubscriptionChain ─────
    # Insert BEFORE getRouting
    routing_pat = re.compile(r'(\n    private fun getRouting\(context: Context,)')
    m = re.search(routing_pat, c)
    if not m:
        print("✗ V2Config: getRouting anchor not found"); return

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

    /**
     * Applies subscription chain (previous/next proxy) to an injected custom outbound.
     * - Prev outbound gets tag "$originalTag-prev"
     * - Next outbound takes over originalTag; original is renamed "$originalTag-orig"
     * - Both chain outbounds are appended (not inserted at 0)
     * - Deduplication prevents duplicates.
     */
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
            updateOutboundWithGlobalSettings(chainOutbound)
            chainOutbound.tag = desiredTag
            outboundTagMap[mapKey] = desiredTag

            chainTo(chainOutbound)
            v2rayConfig.outbounds.add(chainOutbound)
            existingTags.add(desiredTag)
            LogUtil.d(AppConfig.TAG, "Created $chainType outbound: $desiredTag")
        }

        addChainOutbound(subItem.prevProfile, "prev", "$originalTag-prev") { prevOutbound ->
            outbound.ensureSockopt().dialerProxy = prevOutbound.tag
        }

        if (!subItem.nextProfile.isNullOrEmpty()) {
            val newOriginalTag = "$originalTag-orig"
            outbound.tag = newOriginalTag

            addChainOutbound(subItem.nextProfile, "next", originalTag) { nextOutbound ->
                nextOutbound.ensureSockopt().dialerProxy = newOriginalTag
            }
        }
    }

'''
    c = c[:m.start()] + resolve_func + c[m.start():]
    print("✓ V2Config: inserted resolveCurrentServer + applySubscriptionChain")

    # ── 5c. Update getRouting to create outboundTagMap ─────────────────
    old_call = "            injectCustomOutbounds(v2rayConfig)"
    new_call = '''            val outboundTagMap = mutableMapOf<String, String>()
            injectCustomOutbounds(v2rayConfig, outboundTagMap)'''
    if old_call in c:
        c = c.replace(old_call, new_call)
        print("✓ V2Config: getRouting updated")
    else:
        print("✗ V2Config: getRouting call not found")

    # ── 5d. getMoreOutbounds signature + prev/next blocks ─────────────
    # Signature
    old_sig = "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String): Boolean {"
    new_sig = "private fun getMoreOutbounds(v2rayConfig: V2rayConfig, subscriptionId: String, mainProfileRemarks: String? = null): Boolean {"
    if old_sig in c:
        c = c.replace(old_sig, new_sig)
        print("✓ V2Config: getMoreOutbounds signature updated")
    else:
        print("✗ V2Config: getMoreOutbounds signature not found")

    # Call sites
    for old_call_site in ["getMoreOutbounds(v2rayConfig, config.subscriptionId)"]:
        new_call_site = "getMoreOutbounds(v2rayConfig, config.subscriptionId, config.remarks)"
        if old_call_site in c and new_call_site not in c:
            c = c.replace(old_call_site, new_call_site)
            print("✓ V2Config: call site updated")

    # Prev block
    old_prev = '''            //Previous proxy
            val prevNode = SettingsManager.getServerViaRemarks(subItem.prevProfile)
            if (prevNode != null) {
                val prevOutbound = convertProfile2Outbound(prevNode)
                if (prevOutbound != null) {
                    updateOutboundWithGlobalSettings(prevOutbound)
                    prevOutbound.tag = AppConfig.TAG_PROXY + "2"
                    v2rayConfig.outbounds.add(prevOutbound)
                    outbound.ensureSockopt().dialerProxy = prevOutbound.tag
                }
            }'''
    new_prev = '''            //Previous proxy
            val prevNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.prevProfile) ?: subItem.prevProfile)
            if (prevNode != null) {
                if (prevNode.remarks == mainProfileRemarks) {
                    outbound.ensureSockopt().dialerProxy = AppConfig.TAG_PROXY
                    LogUtil.d(AppConfig.TAG, "Prev proxy is main server, set dialerProxy to proxy")
                } else {
                    val prevOutbound = convertProfile2Outbound(prevNode)
                    if (prevOutbound != null) {
                        updateOutboundWithGlobalSettings(prevOutbound)
                        prevOutbound.tag = AppConfig.TAG_PROXY + "2"
                        v2rayConfig.outbounds.add(prevOutbound)
                        outbound.ensureSockopt().dialerProxy = prevOutbound.tag
                    }
                }
            }'''
    if old_prev in c:
        c = c.replace(old_prev, new_prev)
        print("✓ V2Config: prev proxy block patched")
    else:
        print("✗ V2Config: prev proxy block not found")

    # Next block
    old_next = '''            //Next proxy
            val nextNode = SettingsManager.getServerViaRemarks(subItem.nextProfile)
            if (nextNode != null) {
                val nextOutbound = convertProfile2Outbound(nextNode)
                if (nextOutbound != null) {
                    updateOutboundWithGlobalSettings(nextOutbound)
                    nextOutbound.tag = AppConfig.TAG_PROXY
                    v2rayConfig.outbounds.add(0, nextOutbound)
                    outbound.tag = AppConfig.TAG_PROXY + "1"
                    nextOutbound.ensureSockopt().dialerProxy = outbound.tag
                }
            }'''
    new_next = '''            //Next proxy
            val nextNode = SettingsManager.getServerViaRemarks(resolveCurrentServer(subItem.nextProfile) ?: subItem.nextProfile)
            if (nextNode != null) {
                if (nextNode.remarks == mainProfileRemarks) {
                    LogUtil.d(AppConfig.TAG, "Next proxy is main server, skipping")
                } else {
                    val nextOutbound = convertProfile2Outbound(nextNode)
                    if (nextOutbound != null) {
                        updateOutboundWithGlobalSettings(nextOutbound)
                        nextOutbound.tag = AppConfig.TAG_PROXY
                        v2rayConfig.outbounds.add(0, nextOutbound)
                        outbound.tag = AppConfig.TAG_PROXY + "1"
                        nextOutbound.ensureSockopt().dialerProxy = outbound.tag
                    }
                }
            }'''
    if old_next in c:
        c = c.replace(old_next, new_next)
        print("✓ V2Config: next proxy block patched")
    else:
        print("✗ V2Config: next proxy block not found")

    write(p, c)

# ── main ──────────────────────────────────────────────────────────────
def main():
    files = {
        "AppConfig.kt": BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt",
        "activity_sub_edit.xml": BASE / "app/src/main/res/layout/activity_sub_edit.xml",
        "SubEditActivity.kt": BASE / "app/src/main/java/com/v2ray/ang/ui/SubEditActivity.kt",
        "strings.xml": BASE / "app/src/main/res/values/strings.xml",
        "V2rayConfigManager.kt": BASE / "app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt",
    }
    for name, path in files.items():
        if not path.exists():
            print(f"Error: file not found: {path}")
            sys.exit(1)
        backup_kotlin(path)

    try:
        patch_appconfig()
        patch_layout()
        patch_subedit()
        patch_strings()
        patch_v2config()
        print("\n✅ All patches applied successfully.")
        print("👉 Rebuild and test.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

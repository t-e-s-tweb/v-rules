#!/usr/bin/env python3
"""Fix resolveCurrentServer to use MmkvManager.getSelectServer()"""

from pathlib import Path

target = Path("V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt")
content = target.read_text(encoding="utf-8")

old_func = '''private fun resolveCurrentServer(remark: String?): String? {
    if (remark == AppConfig.CURRENT_SERVER) {
        val defaultId = SettingsManager.getDefaultServerId()
        val profile = MmkvManager.decodeServerConfig(defaultId)
        return profile?.remarks
    }
    return remark
}'''

new_func = '''private fun resolveCurrentServer(remark: String?): String? {
    if (remark == AppConfig.CURRENT_SERVER) {
        val currId = MmkvManager.getSelectServer()
        if (!currId.isNullOrEmpty()) {
            val profile = MmkvManager.decodeServerConfig(currId)
            return profile?.remarks
        }
    }
    return remark
}'''

if old_func in content:
    content = content.replace(old_func, new_func)
    target.write_text(content, encoding="utf-8")
    print("✅ resolveCurrentServer fixed.")
else:
    # Maybe already fixed, or different function – check manually
    if "private fun resolveCurrentServer" in content:
        print("⚠️ Function exists but content differs. Check manually.")
    else:
        print("⚠️ resolveCurrentServer not found. Has it been removed?")

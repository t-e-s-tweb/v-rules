#!/usr/bin/env python3
"""
v2rayNG patcher for 2dust/v2rayNG master
  • Adds MASQUE (CONNECT-IP / WARP) outbound protocol support.

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
# 1. EConfigType.kt – add MASQUE enum
# ----------------------------------------------------------------------
def patch_econfigtype():
    p = BASE / "app/src/main/java/com/v2ray/ang/enums/EConfigType.kt"
    if not p.exists():
        print("✗ EConfigType.kt not found")
        return
    c = read(p)

    if re.search(r'\bMASQUE\b', c):
        print("• EConfigType: MASQUE already present")
        return

    old = '    HTTP(10, AppConfig.HTTP),'
    new = '''    HTTP(10, AppConfig.HTTP),
    MASQUE(11, AppConfig.MASQUE),'''
    if old in c:
        c = c.replace(old, new, 1)
        write(p, c)
        print("✓ EConfigType: added MASQUE")
    else:
        print("⚠ EConfigType: HTTP entry not found")


# ----------------------------------------------------------------------
# 2. AppConfig.kt – add MASQUE scheme constant
# ----------------------------------------------------------------------
def patch_appconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/AppConfig.kt"
    if not p.exists():
        print("✗ AppConfig.kt not found")
        return
    c = read(p)

    if re.search(r'\bconst val MASQUE\b', c):
        print("• AppConfig: MASQUE scheme already present")
        return

    old = '    const val HY2 = "hy2://"'
    new = '''    const val HY2 = "hy2://"
    const val MASQUE = "masque://"'''
    if old in c:
        c = c.replace(old, new, 1)
        write(p, c)
        print("✓ AppConfig: added MASQUE scheme")
    else:
        print("⚠ AppConfig: HY2 entry not found")


# ----------------------------------------------------------------------
# 3. ProfileItem.kt – add MASQUE-specific fields
# ----------------------------------------------------------------------
def patch_profileitem():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/entities/ProfileItem.kt"
    if not p.exists():
        print("✗ ProfileItem.kt not found")
        return
    c = read(p)

    if "masqueHost" in c:
        print("• ProfileItem: MASQUE fields already present")
        return

    old = '    var browserDialerMode: String? = null,'
    new = '''    var browserDialerMode: String? = null,

    // MASQUE-specific fields
    var masqueHost: String? = null,
    var masquePath: String? = null,
    var masqueUrl: String? = null,'''
    if old in c:
        c = c.replace(old, new, 1)
        write(p, c)
        print("✓ ProfileItem: added MASQUE fields")
    else:
        print("⚠ ProfileItem: browserDialerMode field not found")


# ----------------------------------------------------------------------
# 4. V2rayConfig.kt – add `masque` field + MasqueConfig class
# ----------------------------------------------------------------------
def patch_v2rayconfig():
    p = BASE / "app/src/main/java/com/v2ray/ang/dto/V2rayConfig.kt"
    if not p.exists():
        print("✗ V2rayConfig.kt not found")
        return
    c = read(p)
    changed = False

    if "MasqueConfig" in c:
        print("• V2rayConfig: MasqueConfig already present")
        return

    # 4a. Add `masque` field to OutSettingsBean
    old_field = '            var remoteDNS: List<String>? = null,\n        ) {'
    new_field = '''            var remoteDNS: List<String>? = null,
            /*Masque*/
            var masque: MasqueConfig? = null,
        ) {'''
    if old_field in c:
        c = c.replace(old_field, new_field, 1)
        changed = True
        print("✓ V2rayConfig: added masque field to OutSettingsBean")
    else:
        print("⚠ V2rayConfig: remoteDNS field boundary not found")

    # 4b. Add MasqueConfig data class after WireGuardBean
    old_bean = '''            data class WireGuardBean(
                var publicKey: String = "",
                var preSharedKey: String? = null,
                var endpoint: String = ""
            )'''
    new_bean = old_bean + '''

            data class MasqueConfig(
                var server: String = "",
                var port: Int = 443,
                var privateKey: String = "",
                var publicKey: String = "",
                var ip: String = "",
                var ipv6: String? = null,
                var mtu: Int? = null,
                var udp: Boolean? = null,
                var remoteDNS: List<String>? = null,
                var host: String? = null,
                var path: String? = null,
                var url: String? = null,
            )'''
    if old_bean in c:
        c = c.replace(old_bean, new_bean, 1)
        changed = True
        print("✓ V2rayConfig: added MasqueConfig data class")
    else:
        print("⚠ V2rayConfig: WireGuardBean not found")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ----------------------------------------------------------------------
# 5. CoreOutboundBuilder.kt
#    5a. dispatch case
#    5b. createInitOutbound MASQUE branch
#    5c. mux-disable list
#    5d. toOutboundMasque function
# ----------------------------------------------------------------------
def patch_coreoutboundbuilder():
    p = BASE / "app/src/main/java/com/v2ray/ang/core/CoreOutboundBuilder.kt"
    if not p.exists():
        print("✗ CoreOutboundBuilder.kt not found")
        return
    c = read(p)
    changed = False

    # 5a. Dispatch
    if "EConfigType.MASQUE -> toOutboundMasque" not in c:
        old_dispatch = '''            EConfigType.HYSTERIA2 -> toOutboundHysteria2(profileItem)
            EConfigType.HTTP -> toOutboundHttp(profileItem)
            else -> null'''
        new_dispatch = '''            EConfigType.HYSTERIA2 -> toOutboundHysteria2(profileItem)
            EConfigType.HTTP -> toOutboundHttp(profileItem)
            EConfigType.MASQUE -> toOutboundMasque(profileItem)
            else -> null'''
        if old_dispatch in c:
            c = c.replace(old_dispatch, new_dispatch, 1)
            changed = True
            print("✓ CoreOutboundBuilder: added MASQUE dispatch case")
        else:
            print("⚠ CoreOutboundBuilder: dispatch switch not found")
    else:
        print("• CoreOutboundBuilder: dispatch case already present")

    # 5b. createInitOutbound MASQUE branch
    if "EConfigType.MASQUE -> OutboundBean(" not in c:
        old_init = '''        EConfigType.HYSTERIA,
        EConfigType.HYSTERIA2 -> OutboundBean(
            protocol = EConfigType.HYSTERIA.name.lowercase(),
            settings = OutSettingsBean(),
            streamSettings = OutboundBean.StreamSettingsBean()
        )

        else -> null'''
        new_init = '''        EConfigType.HYSTERIA,
        EConfigType.HYSTERIA2 -> OutboundBean(
            protocol = EConfigType.HYSTERIA.name.lowercase(),
            settings = OutSettingsBean(),
            streamSettings = OutboundBean.StreamSettingsBean()
        )

        EConfigType.MASQUE -> OutboundBean(
            protocol = EConfigType.MASQUE.name.lowercase(),
            settings = OutSettingsBean(
                secretKey = "",
                masque = OutSettingsBean.MasqueConfig()
            )
        )

        else -> null'''
        if old_init in c:
            c = c.replace(old_init, new_init, 1)
            changed = True
            print("✓ CoreOutboundBuilder: added MASQUE to createInitOutbound")
        else:
            print("⚠ CoreOutboundBuilder: createInitOutbound tail not found")
    else:
        print("• CoreOutboundBuilder: createInitOutbound already has MASQUE")

    # 5c. Mux-disable list
    if "EConfigType.MASQUE.name" not in c:
        old_mux = '''                || protocol.equals(EConfigType.HYSTERIA2.name, true)
                || protocol.equals(EConfigType.HYSTERIA.name, true)
            ) {'''
        new_mux = '''                || protocol.equals(EConfigType.HYSTERIA2.name, true)
                || protocol.equals(EConfigType.HYSTERIA.name, true)
                || protocol.equals(EConfigType.MASQUE.name, true)
            ) {'''
        if old_mux in c:
            c = c.replace(old_mux, new_mux, 1)
            changed = True
            print("✓ CoreOutboundBuilder: added MASQUE to mux-disable list")
        else:
            print("⚠ CoreOutboundBuilder: mux-disable list not matched")
    else:
        print("• CoreOutboundBuilder: mux-disable already includes MASQUE")

    # 5d. Add toOutboundMasque function
    if "private fun toOutboundMasque" not in c:
        last_brace = c.rfind('}')
        if last_brace == -1:
            print("⚠ CoreOutboundBuilder: closing brace not found")
        else:
            masque_func = '''
    private fun toOutboundMasque(profileItem: ProfileItem): OutboundBean? {
        val outboundBean = createInitOutbound(EConfigType.MASQUE) ?: return null

        val rawAddresses = profileItem.localAddress
            ?.split(",")
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?.ifEmpty { null }
            ?: listOf(AppConfig.WIREGUARD_LOCAL_ADDRESS_V4)

        val addresses = if (MmkvManager.decodeSettingsBool(AppConfig.PREF_IPV6_ENABLED) == true) {
            rawAddresses
        } else {
            val ipv4Addresses = rawAddresses.filter { !it.contains(":") }
            ipv4Addresses.ifEmpty { listOf(AppConfig.WIREGUARD_LOCAL_ADDRESS_V4) }
        }

        val rawDNS = profileItem.remoteDNS
            ?.split(",")
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?.ifEmpty { null }
            ?: listOf(AppConfig.WIREGUARD_LOCAL_REMOTE_DNS)

        val remotes = if (MmkvManager.decodeSettingsBool(AppConfig.PREF_IPV6_ENABLED) == true) {
            rawDNS
        } else {
            val ipv4Dns = rawDNS.filter { !it.contains(":") }
            ipv4Dns.ifEmpty { listOf(AppConfig.WIREGUARD_LOCAL_REMOTE_DNS) }
        }

        val serverAddr = getServerAddress(profileItem)
        val serverPort = profileItem.serverPort.orEmpty().toIntOrNull() ?: 443

        outboundBean.settings?.let { settings ->
            settings.address = serverAddr
            settings.port = serverPort
            settings.secretKey = profileItem.secretKey
            settings.mtu = profileItem.mtu
            settings.remoteDNS = remotes
            settings.masque = OutboundBean.OutSettingsBean.MasqueConfig(
                server = serverAddr,
                port = serverPort,
                privateKey = profileItem.secretKey.orEmpty(),
                publicKey = profileItem.publicKey.orEmpty(),
                ip = addresses.firstOrNull() ?: AppConfig.WIREGUARD_LOCAL_ADDRESS_V4,
                ipv6 = addresses.firstOrNull { it.contains(":") },
                mtu = profileItem.mtu,
                udp = true,
                remoteDNS = remotes,
                host = profileItem.masqueHost,
                path = profileItem.masquePath,
                url = profileItem.masqueUrl,
            )
        }

        return outboundBean
    }
'''
            c = c[:last_brace] + masque_func + c[last_brace:]
            changed = True
            print("✓ CoreOutboundBuilder: added toOutboundMasque function")
    else:
        print("• CoreOutboundBuilder: toOutboundMasque already present")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ----------------------------------------------------------------------
# 6. MasqueFmt.kt – new formatter
# ----------------------------------------------------------------------
def create_masque_formatter():
    p = BASE / "app/src/main/java/com/v2ray/ang/fmt/MasqueFmt.kt"
    if p.exists():
        print("• MasqueFmt.kt already exists")
        return

    content = '''package com.v2ray.ang.fmt

import com.v2ray.ang.AppConfig
import com.v2ray.ang.dto.entities.ProfileItem
import com.v2ray.ang.enums.EConfigType
import com.v2ray.ang.extension.idnHost
import com.v2ray.ang.extension.nullIfBlank
import com.v2ray.ang.extension.removeWhiteSpace
import com.v2ray.ang.util.Utils
import java.net.URI

object MasqueFmt : FmtBase() {
    fun parse(str: String): ProfileItem? {
        val config = ProfileItem.create(EConfigType.MASQUE)

        val uri = URI(Utils.fixIllegalUrl(str))
        if (uri.rawQuery.isNullOrEmpty()) return null
        val queryParam = getQueryParam(uri)

        config.remarks = Utils.decodeURIComponent(uri.fragment.orEmpty()).let { it.ifEmpty { "none" } }
        config.server = uri.idnHost
        config.serverPort = uri.port.toString()

        config.secretKey = uri.userInfo.orEmpty()
        config.localAddress = queryParam["address"] ?: AppConfig.WIREGUARD_LOCAL_ADDRESS_V4
        config.publicKey = queryParam["publickey"].orEmpty()
        config.preSharedKey = queryParam["presharedkey"]?.nullIfBlank()
        config.mtu = Utils.parseInt(queryParam["mtu"] ?: AppConfig.WIREGUARD_LOCAL_MTU)
        config.remoteDNS = queryParam["dns"] ?: AppConfig.WIREGUARD_LOCAL_REMOTE_DNS
        config.reserved = queryParam["reserved"] ?: "0,0,0"
        config.masqueHost = queryParam["host"]
        config.masquePath = queryParam["path"]
        config.masqueUrl = queryParam["url"]
        config.finalMask = (queryParam["fm"] ?: queryParam["finalmask"] ?: queryParam["finalMask"])?.nullIfBlank()

        return config
    }

    fun toUri(config: ProfileItem): String {
        val dicQuery = HashMap<String, String>()

        dicQuery["publickey"] = config.publicKey.orEmpty()
        if (config.reserved != null) {
            dicQuery["reserved"] = config.reserved.removeWhiteSpace().orEmpty()
        }
        dicQuery["address"] = config.localAddress.removeWhiteSpace().orEmpty()
        if (config.mtu != null) {
            dicQuery["mtu"] = config.mtu.toString()
        }
        if (config.preSharedKey != null) {
            dicQuery["presharedkey"] = config.preSharedKey.removeWhiteSpace().orEmpty()
        }
        if (config.remoteDNS != null) {
            dicQuery["dns"] = config.remoteDNS.removeWhiteSpace().orEmpty()
        }
        config.masqueHost?.let { dicQuery["host"] = it }
        config.masquePath?.let { dicQuery["path"] = it }
        config.masqueUrl?.let { dicQuery["url"] = it }
        config.finalMask?.nullIfBlank()?.let { dicQuery["fm"] = it }

        return toUri(config, config.secretKey, dicQuery)
    }
}
'''
    p.write_text(content, encoding="utf-8")
    print("✓ Created MasqueFmt.kt")


# ----------------------------------------------------------------------
# 7. AngConfigManager.kt – register MASQUE formatter + share case
# ----------------------------------------------------------------------
def patch_angconfigmanager():
    p = BASE / "app/src/main/java/com/v2ray/ang/handler/AngConfigManager.kt"
    if not p.exists():
        print("✗ AngConfigManager.kt not found")
        return
    c = read(p)
    changed = False

    if "import com.v2ray.ang.fmt.MasqueFmt" not in c:
        c = c.replace(
            "import com.v2ray.ang.fmt.Hysteria2Fmt",
            "import com.v2ray.ang.fmt.Hysteria2Fmt\nimport com.v2ray.ang.fmt.MasqueFmt",
            1,
        )
        changed = True
        print("✓ AngConfigManager: added MasqueFmt import")

    old_map = '''            EConfigType.HYSTERIA2.protocolScheme to Hysteria2Fmt::parse,
            AppConfig.HY2 to Hysteria2Fmt::parse,'''
    new_map = '''            EConfigType.HYSTERIA2.protocolScheme to Hysteria2Fmt::parse,
            EConfigType.MASQUE.protocolScheme to MasqueFmt::parse,
            AppConfig.HY2 to Hysteria2Fmt::parse,'''
    if "EConfigType.MASQUE.protocolScheme to MasqueFmt::parse" not in c:
        if old_map in c:
            c = c.replace(old_map, new_map, 1)
            changed = True
            print("✓ AngConfigManager: registered MasqueFmt in parser map")
        else:
            print("⚠ AngConfigManager: parser map insertion point not found")
    else:
        print("• AngConfigManager: MasqueFmt already in parser map")

    # shareConfig: add MASQUE case
    old_share = '''                EConfigType.HYSTERIA2 -> Hysteria2Fmt.toUri(config)
                else -> {}'''
    new_share = '''                EConfigType.HYSTERIA2 -> Hysteria2Fmt.toUri(config)
                EConfigType.MASQUE -> MasqueFmt.toUri(config)
                else -> {}'''
    if "EConfigType.MASQUE -> MasqueFmt.toUri" not in c:
        if old_share in c:
            c = c.replace(old_share, new_share, 1)
            changed = True
            print("✓ AngConfigManager: added MASQUE to shareConfig")
        else:
            print("⚠ AngConfigManager: shareConfig HYSTERIA2 not found")
    else:
        print("• AngConfigManager: MASQUE share case already present")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ----------------------------------------------------------------------
# 8. strings.xml – MASQUE UI strings
# ----------------------------------------------------------------------
def patch_strings():
    p = BASE / "app/src/main/res/values/strings.xml"
    if not p.exists():
        print("✗ strings.xml not found")
        return
    c = read(p)

    needed = {
        "menu_item_import_config_manually_masque": "Add [MASQUE]",
        "server_lab_masque_host": "MASQUE Host (optional)",
        "server_lab_masque_path": "MASQUE Path (optional)",
        "server_lab_masque_url": "MASQUE URL (optional)",
    }
    new_strings = []
    for k, v in needed.items():
        if f'name="{k}"' in c:
            continue
        new_strings.append(f'    <string name="{k}">{v}</string>')

    if not new_strings:
        print("• strings.xml: MASQUE strings already present")
        return

    m = re.search(r'(\s*)</resources>', c, re.IGNORECASE)
    if m:
        indent, pos = m.group(1), m.start()
        insertion = "\n" + "\n".join(new_strings) + "\n" + indent
        c = c[:pos] + insertion + c[pos:]
        write(p, c)
        print(f"✓ strings.xml: added {len(new_strings)} MASQUE strings")
    else:
        print("⚠ strings.xml: </resources> not found")


# ----------------------------------------------------------------------
# 9. ServerMasqueActivity.kt
# ----------------------------------------------------------------------
def create_server_activity():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/server/ServerMasqueActivity.kt"
    if p.exists():
        print("• ServerMasqueActivity.kt already exists")
        return

    content = '''package com.v2ray.ang.ui.server

import androidx.compose.runtime.Composable
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.res.stringResource
import com.v2ray.ang.R
import com.v2ray.ang.enums.EConfigType
import com.v2ray.ang.ui.compose.FormTextField

class ServerMasqueActivity : BaseServerActivity() {

    override val serverConfigType: EConfigType = EConfigType.MASQUE

    @Composable
    override fun ScreenContent() {
        val uiState = rememberSaveable(saver = ServerUiState.Saver) {
            ServerUiState.from(
                initialConfig = initialConfig
            )
        }.apply {
            configType = EConfigType.MASQUE
        }

        ServerEditorScaffold(
            title = serverConfigType.toString(),
            onSaveClick = { saveServer(uiState) }
        ) {
            CommonBasicFields(uiState)
            MasqueProtocolFields(uiState)
        }
    }

    @Composable
    private fun MasqueProtocolFields(state: ServerUiState) {
        FormTextField(
            stringResource(R.string.server_lab_secret_key),
            state.secretKey,
            { state.secretKey = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_public_key),
            state.publicKey,
            { state.publicKey = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_preshared_key),
            state.preSharedKey,
            { state.preSharedKey = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_local_address),
            state.localAddress,
            { state.localAddress = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_local_mtu),
            state.mtu,
            { state.mtu = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_remote_dns),
            state.remoteDNS,
            { state.remoteDNS = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_masque_host),
            state.masqueHost,
            { state.masqueHost = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_masque_path),
            state.masquePath,
            { state.masquePath = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_masque_url),
            state.masqueUrl,
            { state.masqueUrl = it }
        )
        FormTextField(
            stringResource(R.string.server_lab_final_mask),
            state.finalMask,
            { state.finalMask = it }
        )
    }
}
'''
    p.write_text(content, encoding="utf-8")
    print("✓ Created ServerMasqueActivity.kt")


# ----------------------------------------------------------------------
# 10. ServerUiState.kt – add MASQUE fields (FIXED)
# ----------------------------------------------------------------------
def patch_serveruistate():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/server/ServerUiState.kt"
    if not p.exists():
        print("✗ ServerUiState.kt not found")
        return
    c = read(p)

    if "masqueHost" in c:
        print("• ServerUiState: MASQUE fields already present")
        return

    changed = False

    # (a) primary constructor param — NO `var`, matches the actual file
    old_ctor = '    browserDialerMode: String = "",'
    new_ctor = '''    browserDialerMode: String = "",
    masqueHost: String = "",
    masquePath: String = "",
    masqueUrl: String = "",'''
    if old_ctor in c:
        c = c.replace(old_ctor, new_ctor, 1)
        changed = True
        print("✓ ServerUiState: added MASQUE constructor params")
    else:
        print("⚠ ServerUiState: browserDialerMode constructor param not found")

    # (b) class body property delegate
    old_prop = '    var browserDialerMode by mutableStateOf(browserDialerMode)'
    new_prop = '''    var browserDialerMode by mutableStateOf(browserDialerMode)
    var masqueHost by mutableStateOf(masqueHost)
    var masquePath by mutableStateOf(masquePath)
    var masqueUrl by mutableStateOf(masqueUrl)'''
    if old_prop in c:
        c = c.replace(old_prop, new_prop, 1)
        changed = True
        print("✓ ServerUiState: added MASQUE property delegates")
    else:
        print("⚠ ServerUiState: browserDialerMode property not found")

    # (c) fromProfileItem: append masque fields after the browserDialerMode line
    m = re.search(
        r'^(\s*)browserDialerMode\s*=\s*initialConfig\.browserDialerMode.*$',
        c, re.MULTILINE,
    )
    if m and "masqueHost = initialConfig.masqueHost" not in c:
        indent = m.group(1)
        addition = (
            f"\n{indent}masqueHost = initialConfig.masqueHost ?: \"\","
            f"\n{indent}masquePath = initialConfig.masquePath ?: \"\","
            f"\n{indent}masqueUrl = initialConfig.masqueUrl ?: \"\","
        )
        c = c[:m.end()] + addition + c[m.end():]
        changed = True
        print("✓ ServerUiState: added MASQUE fields to fromProfileItem")
    elif m:
        print("• ServerUiState: fromProfileItem already has MASQUE")
    else:
        print("⚠ ServerUiState: fromProfileItem mapping not found")

    # (d) toProfileItem: append masque fields after the browserDialerMode block
    old_to = '''            browserDialerMode = if (network in listOf(NetworkType.WS.type, NetworkType.XHTTP.type)) {
                browserDialerMode.nullIfBlank()
            } else {
                null
            },'''
    new_to = old_to + '''
            masqueHost = masqueHost.nullIfBlank(),
            masquePath = masquePath.nullIfBlank(),
            masqueUrl = masqueUrl.nullIfBlank(),'''
    if "masqueHost = masqueHost.nullIfBlank()" not in c:
        if old_to in c:
            c = c.replace(old_to, new_to, 1)
            changed = True
            print("✓ ServerUiState: added MASQUE fields to toProfileItem")
        else:
            print("⚠ ServerUiState: toProfileItem browserDialerMode block not found")
    else:
        print("• ServerUiState: toProfileItem already has MASQUE")

    if changed:
        backup_kotlin(p)
        write(p, c)


# ----------------------------------------------------------------------
# 11. MainActivity.kt – MASQUE import branch
# ----------------------------------------------------------------------
def patch_mainactivity():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/main/MainActivity.kt"
    if not p.exists():
        print("✗ MainActivity.kt not found")
        return
    c = read(p)

    if "ServerMasqueActivity" in c:
        print("• MainActivity: MASQUE import branch already present")
        return

    old = '            EConfigType.HYSTERIA2.value -> Intent(this, ServerHysteria2Activity::class.java)'
    new = '''            EConfigType.HYSTERIA2.value -> Intent(this, ServerHysteria2Activity::class.java)
            EConfigType.MASQUE.value -> Intent(this, ServerMasqueActivity::class.java)'''
    if old in c:
        c = c.replace(old, new, 1)
        backup_kotlin(p)
        write(p, c)
        print("✓ MainActivity: added MASQUE import branch")
    else:
        print("⚠ MainActivity: HYSTERIA2 import branch not found")


# ----------------------------------------------------------------------
# 12. MainImportMenu.kt – add MASQUE entry
# ----------------------------------------------------------------------
def patch_mainimportmenu():
    p = BASE / "app/src/main/java/com/v2ray/ang/ui/main/MainImportMenu.kt"
    if not p.exists():
        print("✗ MainImportMenu.kt not found")
        return
    c = read(p)

    if "EConfigType.MASQUE.value" in c:
        print("• MainImportMenu: MASQUE entry already present")
        return

    old = '    Hysteria2(R.string.menu_item_import_config_manually_hysteria2, MainAction.ImportManually(EConfigType.HYSTERIA2.value))'
    new = '''    Hysteria2(R.string.menu_item_import_config_manually_hysteria2, MainAction.ImportManually(EConfigType.HYSTERIA2.value)),
    Masque(R.string.menu_item_import_config_manually_masque, MainAction.ImportManually(EConfigType.MASQUE.value))'''
    if old in c:
        c = c.replace(old, new, 1)
        backup_kotlin(p)
        write(p, c)
        print("✓ MainImportMenu: added MASQUE entry")
    else:
        print("⚠ MainImportMenu: Hysteria2 enum entry not found")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Patcher: Add MASQUE (CONNECT-IP / WARP) outbound support")
    print("=" * 70)
    try:
        patch_econfigtype()
        patch_appconfig()
        patch_profileitem()
        patch_v2rayconfig()
        patch_coreoutboundbuilder()
        create_masque_formatter()
        patch_angconfigmanager()
        patch_strings()
        create_server_activity()
        patch_serveruistate()
        patch_mainactivity()
        patch_mainimportmenu()
        print("\n✅ Done.")
        print("👉 Rebuild and test.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

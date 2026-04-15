#!/usr/bin/env python3
import os
import re


def read_file(path, encoding=None):
    with open(path, "r", encoding=encoding) as f:
        return f.read()


def write_file(path, content, encoding=None):
    with open(path, "w", encoding=encoding) as f:
        f.write(content)


def modify_ruleset_item():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/dto/RulesetItem.kt"
    if not os.path.exists(filepath):
        return False

    content = read_file(filepath)

    if "var customOutboundTag: String? = null" in content:
        print("  ✓ RulesetItem.kt (already patched)")
        return True

    old = '    var locked: Boolean? = false,'
    new = old + '\n    var customOutboundTag: String? = null,'

    if old not in content:
        print("  ✗ Could not find insertion point in RulesetItem.kt")
        return False

    content = content.replace(old, new)
    write_file(filepath, content)

    print("  ✓ RulesetItem.kt")
    return True


def modify_arrays_xml():
    filepath = "V2rayNG/app/src/main/res/values/arrays.xml"
    if not os.path.exists(filepath):
        return False

    content = read_file(filepath)

    if "<item>custom</item>" in content:
        print("  ✓ arrays.xml (already patched)")
        return True

    old = "<item>block</item>"
    new = old + "\n        <item>custom</item>"

    if old not in content:
        print("  ✗ Could not find insertion point in arrays.xml")
        return False

    content = content.replace(old, new)
    write_file(filepath, content)

    print("  ✓ arrays.xml")
    return True


def modify_layout():
    filepath = "V2rayNG/app/src/main/res/layout/activity_routing_edit.xml"
    if not os.path.exists(filepath):
        return False

    content = read_file(filepath)

    if 'android:id="@+id/layout_custom_outbound"' in content:
        print("  ✓ activity_routing_edit.xml (already patched)")
        return True

    m = re.search(r'android:entries="@array/outbound_tag"\s*/>', content)
    if not m:
        print("  ✗ Could not find spinner in layout")
        return False

    after = content[m.end():]
    cm = re.search(r'(\s*)</LinearLayout>', after)
    if not cm:
        print("  ✗ Could not find parent LinearLayout closing tag")
        return False

    indent = cm.group(1)
    insert_at = m.end() + cm.start()
    end_at = insert_at + len(cm.group(0))

    new_layout = f"""\
{indent}<LinearLayout
{indent}    android:id="@+id/layout_custom_outbound"
{indent}    android:layout_width="match_parent"
{indent}    android:layout_height="wrap_content"
{indent}    android:layout_marginTop="@dimen/padding_spacing_dp16"
{indent}    android:orientation="vertical"
{indent}    android:visibility="gone">
{indent}    <TextView
{indent}        android:layout_width="wrap_content"
{indent}        android:layout_height="wrap_content"
{indent}        android:text="@string/routing_settings_custom_outbound_tag" />
{indent}    <EditText
{indent}        android:id="@+id/et_custom_outbound_tag"
{indent}        android:layout_width="match_parent"
{indent}        android:layout_height="wrap_content"
{indent}        android:inputType="text"
{indent}        android:hint="@string/routing_settings_custom_outbound_hint" />
{indent}</LinearLayout>
"""

    content = content[:end_at] + new_layout + content[end_at:]
    write_file(filepath, content)

    print("  ✓ activity_routing_edit.xml")
    return True


def modify_strings_xml():
    filepath = "V2rayNG/app/src/main/res/values/strings.xml"
    if not os.path.exists(filepath):
        return False

    content = read_file(filepath, encoding="utf-8")

    needed = {
        "routing_settings_custom_outbound_tag": "Custom outbound tag",
        "routing_settings_custom_outbound_hint": "Enter profile/group remark",
        "routing_settings_custom_outbound_empty": "Custom outbound tag cannot be empty",
    }

    changed = False

    for k, v in needed.items():
        if f'name="{k}"' in content:
            continue

        m = re.search(r"(\s*)</resources>", content, re.IGNORECASE)
        if not m:
            print(f"  ✗ Could not insert '{k}'")
            return False

        indent = m.group(1)
        pos = m.start()

        insert = f'\n{indent}<string name="{k}">{v}</string>'
        content = content[:pos] + insert + content[pos:]
        changed = True

    if changed:
        write_file(filepath, content, encoding="utf-8")

    print("  ✓ strings.xml")
    return True


def modify_routing_edit_activity():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/ui/RoutingEditActivity.kt"
    if not os.path.exists(filepath):
        return False

    content = read_file(filepath)

    if "CUSTOM_OUTBOUND_INDEX = 3" in content:
        print("  ✓ RoutingEditActivity.kt (already patched)")
        return True

    # Import
    if "isNotNullEmpty" not in content:
        content = content.replace(
            "nullIfBlank",
            "nullIfBlank\nimport com.v2ray.ang.extension.isNotNullEmpty"
        )

    # Constant
    old_const = """    private val outbound_tag: Array<out String> by lazy {
        resources.getStringArray(R.array.outbound_tag)
    }"""

    new_const = old_const + """

    // custom index
    private val CUSTOM_OUTBOUND_INDEX = 3"""

    if old_const not in content:
        print("  ✗ outbound_tag not found")
        return False

    content = content.replace(old_const, new_const)

    # Save patch
    old_save = "outboundTag = outbound_tag[binding.spOutboundTag.selectedItemPosition]"

    new_save = """// Handle custom outbound tag
            val pos = binding.spOutboundTag.selectedItemPosition
            if (pos == CUSTOM_OUTBOUND_INDEX) {
                val custom = binding.etCustomOutboundTag.text.toString().trim()
                if (custom.isEmpty()) {
                    toast(R.string.routing_settings_custom_outbound_empty)
                    return false
                }
                outboundTag = custom
                customOutboundTag = custom
            } else {
                outboundTag = outbound_tag[pos]
                customOutboundTag = null
            }"""

    if old_save in content:
        content = content.replace(old_save, new_save)

    write_file(filepath, content)

    print("  ✓ RoutingEditActivity.kt")
    return True


def modify_v2ray_config_manager():
    filepath = "V2rayNG/app/src/main/java/com/v2ray/ang/handler/V2rayConfigManager.kt"
    if not os.path.exists(filepath):
        return False

    content = read_file(filepath)

    if "isCustomOutboundTag" in content:
        print("  ✓ V2rayConfigManager.kt (already patched)")
        return True

    insert = """
    private fun isCustomOutboundTag(tag: String): Boolean {
        return tag != AppConfig.TAG_PROXY &&
               tag != AppConfig.TAG_DIRECT &&
               tag != AppConfig.TAG_BLOCKED
    }
"""

    anchor = "return domain"

    if anchor not in content:
        print("  ✗ anchor not found")
        return False

    content = content.replace(anchor, anchor + insert)

    write_file(filepath, content)

    print("  ✓ V2rayConfigManager.kt")
    return True


def main():
    print("=" * 60)
    print("Custom Outbound Patcher (Clean)")
    print("=" * 60)

    funcs = [
        ("RulesetItem.kt", modify_ruleset_item),
        ("arrays.xml", modify_arrays_xml),
        ("layout", modify_layout),
        ("strings.xml", modify_strings_xml),
        ("RoutingEditActivity.kt", modify_routing_edit_activity),
        ("V2rayConfigManager.kt", modify_v2ray_config_manager),
    ]

    results = []

    for name, func in funcs:
        try:
            ok = func()
            results.append(ok)
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            results.append(False)

    success = sum(results)

    print("\n" + "=" * 60)
    print(f"✅ {success}/{len(results)} patched")

    if success == len(results):
        print("👉 Rebuild the app")
    else:
        print("❌ Some patches failed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
v2rayNG – Replace FormDropdownField with searchable lazy dropdown (Popup + LazyColumn)
Fixed imports: removed bogus 'weight' import, added 'remember'.
"""

import os
import re
import sys

FORM_FIELDS_FILE = "V2rayNG/app/src/main/java/com/v2ray/ang/compose/FormFields.kt"

NEW_FUNCTION = """
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FormDropdownField(
    label: String,
    value: String,
    options: List<String>,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    editable: Boolean = false,
    enabled: Boolean = true,
    placeholder: String? = null,
) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    var searchQuery by rememberSaveable { mutableStateOf("") }
    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current

    val filteredOptions = remember(options, searchQuery) {
        if (searchQuery.isEmpty()) options
        else options.filter { it.contains(searchQuery, ignoreCase = true) }
    }

    Box(modifier = modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
        OutlinedTextField(
            value = value,
            onValueChange = { if (editable) onValueChange(it) },
            readOnly = !editable,
            enabled = enabled,
            label = { Text(label) },
            placeholder = { if (placeholder != null) Text(placeholder) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = Color.Transparent,
                unfocusedContainerColor = Color.Transparent,
                cursorColor = MaterialTheme.colorScheme.secondary,
                selectionColors = TextSelectionColors(
                    handleColor = MaterialTheme.colorScheme.secondary,
                    backgroundColor = MaterialTheme.colorScheme.secondary.copy(alpha = 0.4f)
                )
            ),
            modifier = Modifier
                .fillMaxWidth()
                .onFocusChanged { focusState ->
                    if (!editable && focusState.isFocused) {
                        keyboardController?.hide()
                    }
                }
                .clickable(enabled = enabled) {
                    if (!editable) {
                        expanded = true
                        keyboardController?.hide()
                    }
                }
        )

        if (expanded) {
            Popup(
                onDismissRequest = { expanded = false },
                alignment = Alignment.TopStart
            ) {
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 300.dp),
                    shape = MaterialTheme.shapes.extraSmall,
                    tonalElevation = 4.dp,
                    color = MaterialTheme.colorScheme.surface
                ) {
                    Column {
                        OutlinedTextField(
                            value = searchQuery,
                            onValueChange = { searchQuery = it },
                            placeholder = { Text("Search...") },
                            singleLine = true,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(8.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedContainerColor = Color.Transparent,
                                unfocusedContainerColor = Color.Transparent,
                                cursorColor = MaterialTheme.colorScheme.secondary,
                                selectionColors = TextSelectionColors(
                                    handleColor = MaterialTheme.colorScheme.secondary,
                                    backgroundColor = MaterialTheme.colorScheme.secondary.copy(alpha = 0.4f)
                                )
                            )
                        )
                        Divider()
                        LazyColumn(modifier = Modifier.weight(1f)) {
                            items(filteredOptions) { option ->
                                DropdownMenuItem(
                                    text = { Text(option) },
                                    onClick = {
                                        onValueChange(option)
                                        expanded = false
                                        searchQuery = ""
                                        focusManager.clearFocus()
                                    }
                                )
                            }
                            if (filteredOptions.isEmpty()) {
                                item {
                                    DropdownMenuItem(
                                        text = { Text("No results") },
                                        onClick = { }
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
"""

# Correct imports – removed `import androidx.compose.foundation.layout.weight`
REQUIRED_IMPORTS = [
    "import androidx.compose.foundation.layout.Box",
    "import androidx.compose.foundation.layout.Column",
    "import androidx.compose.foundation.layout.fillMaxWidth",
    "import androidx.compose.foundation.layout.padding",
    "import androidx.compose.foundation.layout.heightIn",
    "import androidx.compose.foundation.lazy.LazyColumn",
    "import androidx.compose.foundation.lazy.items",
    "import androidx.compose.foundation.clickable",
    "import androidx.compose.material3.Divider",
    "import androidx.compose.material3.Popup",
    "import androidx.compose.material3.Surface",
    "import androidx.compose.runtime.mutableStateOf",
    "import androidx.compose.runtime.remember",
    "import androidx.compose.runtime.saveable.rememberSaveable",
    "import androidx.compose.runtime.setValue",
    "import androidx.compose.runtime.getValue",
    "import androidx.compose.ui.Alignment",
    "import androidx.compose.ui.unit.dp",
]


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def find_function_brace(content, func_name):
    pattern = r"fun\s+" + re.escape(func_name) + r"\s*\([^)]*\)\s*[:=]?\s*[^{]*\{"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    brace_pos = match.end() - 1
    depth = 0
    end = -1
    for i in range(brace_pos, len(content)):
        ch = content[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return None
    return start, end


def replace_function(content, func_name, new_body):
    pos = find_function_brace(content, func_name)
    if not pos:
        print(f"[ERROR] Could not find function {func_name}")
        return content
    start, end = pos
    return content[:start] + new_body + content[end+1:]


def main(project_root):
    form_path = os.path.join(project_root, FORM_FIELDS_FILE)
    if not os.path.isfile(form_path):
        print(f"[ERROR] File not found: {form_path}")
        sys.exit(1)

    content = read_file(form_path)

    # Add missing imports
    import_block = ""
    for imp in REQUIRED_IMPORTS:
        if imp not in content:
            import_block += imp + "\n"

    if import_block:
        import_pattern = r"(import .*\n)+"
        import_match = re.search(import_pattern, content)
        if import_match:
            insert_pos = import_match.end()
            content = content[:insert_pos] + import_block + content[insert_pos:]
            print("[INFO] Added required imports")
        else:
            print("[WARNING] Could not find import block; adding at top")
            content = import_block + content

    # Replace the function
    content = replace_function(content, "FormDropdownField", NEW_FUNCTION)
    print("[INFO] Replaced FormDropdownField with lazy searchable version")

    write_file(form_path, content)
    print("[DONE] FormFields.kt patched.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fix_dropdown_lazy_final.py <project_root>")
        sys.exit(1)
    main(sys.argv[1])

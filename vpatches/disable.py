#!/usr/bin/env python3
"""
disable_release_shrinking.py

Sets isMinifyEnabled and isShrinkResources to false inside the `release`
build type of an Android Gradle Kotlin DSL file (app/build.gradle.kts).
Only that block is touched -- other build types (debug, nightly, etc.)
are left exactly as they are, even if they also set isMinifyEnabled/
isShrinkResources.

Path resolution (first match wins):
  1. GRADLE_FILE_PATH  - exact path to build.gradle.kts, if set
  2. GITHUB_WORKSPACE  - CI checkout root; script appends app/build.gradle.kts
  3. ./app/build.gradle.kts - local fallback

Usage:
  GRADLE_FILE_PATH=/path/to/app/build.gradle.kts python3 disable_release_shrinking.py
  # or, in GitHub Actions, GITHUB_WORKSPACE is already set for you:
  python3 disable_release_shrinking.py

  Add --dry-run to preview the change without writing the file.
"""

import os
import re
import sys

FILE_PATH_ENV = "GRADLE_FILE_PATH"
WORKSPACE_ENV = "GITHUB_WORKSPACE"
DEFAULT_RELATIVE_PATH = "app/build.gradle.kts"

FLAGS_TO_DISABLE = ("isMinifyEnabled", "isShrinkResources")


def resolve_path() -> str:
    if os.environ.get(FILE_PATH_ENV):
        return os.environ[FILE_PATH_ENV]
    if os.environ.get(WORKSPACE_ENV):
        return os.path.join(os.environ[WORKSPACE_ENV], "app", "build.gradle.kts")
    return DEFAULT_RELATIVE_PATH


def find_top_level_block(text: str, block_name: str):
    """
    Find a top-level `<block_name> { ... }` block, where block_name must be
    the first token on its line (so e.g. `getByName("release")` or
    `create("release")` never match). Returns (open_brace_idx,
    one_past_close_brace_idx, block_text), or None if not found.
    """
    match = re.search(rf'^[ \t]*{re.escape(block_name)}[ \t]*\{{', text, re.MULTILINE)
    if not match:
        return None

    open_idx = text.index("{", match.start())
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return open_idx, i + 1, text[open_idx:i + 1]
    return None  # unbalanced braces -- shouldn't happen on valid Kotlin


def set_boolean_flag(block_text: str, flag_name: str, new_value: str):
    """
    Set `flag_name = <bool>` to `flag_name = new_value` inside block_text.
    Returns (new_block_text, status, old_line, new_line) where status is
    one of "changed", "unchanged", "missing".
    """
    pattern = re.compile(
        rf'^([ \t]*){re.escape(flag_name)}[ \t]*=[ \t]*(\w+)',
        re.MULTILINE,
    )
    match = pattern.search(block_text)
    if not match:
        return block_text, "missing", None, None

    indent, current_value = match.group(1), match.group(2)
    old_line = match.group(0).strip()

    if current_value == new_value:
        return block_text, "unchanged", old_line, old_line

    new_line = f"{flag_name} = {new_value}"
    new_block_text = block_text[:match.start()] + indent + new_line + block_text[match.end():]
    return new_block_text, "changed", old_line, new_line


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    path = resolve_path()

    if not os.path.isfile(path):
        print(f"error: file not found: {path}", file=sys.stderr)
        print(f"  set {FILE_PATH_ENV} (or {WORKSPACE_ENV}) to point at the "
              f"correct app/build.gradle.kts", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8", newline="") as f:
        original_text = f.read()

    block = find_top_level_block(original_text, "release")
    if block is None:
        print(f"error: could not find a top-level `release {{ ... }}` block in {path}",
              file=sys.stderr)
        sys.exit(1)
    block_start, block_end, block_text = block

    working_text = block_text
    changes = []
    for flag in FLAGS_TO_DISABLE:
        working_text, status, old_line, new_line = set_boolean_flag(working_text, flag, "false")
        changes.append((flag, status, old_line, new_line))
    new_block_text = working_text

    updated_text = original_text[:block_start] + new_block_text + original_text[block_end:]

    print(f"file: {path}\n")
    print("release {} changes:")
    any_changed = False
    for flag, status, old_line, new_line in changes:
        if status == "changed":
            any_changed = True
            print(f"  - {old_line}")
            print(f"  + {new_line}")
        elif status == "unchanged":
            print(f"  = {old_line}   (already false, no change)")
        else:
            print(f"  ! {flag} not found inside release {{}} -- left untouched")

    print("\nrelease {} block for reference (after changes):")
    print(new_block_text.rstrip())

    if not any_changed:
        print("\nno changes needed; file left as-is")
        return

    if dry_run:
        print(f"\n--dry-run set: {path} was NOT modified")
        return

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(updated_text)

    print(f"\nwrote changes to {path}")


if __name__ == "__main__":
    main()

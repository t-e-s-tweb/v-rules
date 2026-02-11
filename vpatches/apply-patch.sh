#!/bin/bash
#
# Script to apply the custom outbound routing patch to v2rayNG
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V2RAYNG_DIR="${1:-.}"

echo "=========================================="
echo "v2rayNG Custom Outbound Routing Patch"
echo "=========================================="
echo ""

if [ ! -d "$V2RAYNG_DIR" ]; then
    echo "Error: v2rayNG directory not found at: $V2RAYNG_DIR"
    echo "Usage: $0 <path-to-v2rayNG-directory>"
    exit 1
fi

cd "$V2RAYNG_DIR"

# Check if we're in the right directory
if [ ! -f "app/src/main/java/com/v2ray/ang/AppConfig.kt" ]; then
    echo "Error: This doesn't appear to be the v2rayNG repository"
    echo "Please run this script from the v2rayNG root directory"
    exit 1
fi

echo "Target directory: $(pwd)"
echo ""

# Apply the main patch
echo "Applying custom outbound routing patch..."
if git apply --check "$SCRIPT_DIR/custom-outbound-routing.patch" 2>/dev/null; then
    git apply "$SCRIPT_DIR/custom-outbound-routing.patch" --ignore-whitespace
    echo "✓ Main patch applied successfully"
else
    echo "⚠ Patch may have already been applied or there are conflicts"
    echo "Attempting to apply with --3way..."
    if git apply --3way "$SCRIPT_DIR/custom-outbound-routing.patch" --ignore-whitespace; then
        echo "✓ Main patch applied with 3-way merge"
    else
        echo "✗ Failed to apply main patch"
        exit 1
    fi
fi

# Apply strings patch if it exists
if [ -f "$SCRIPT_DIR/strings.xml additions.patch" ]; then
    echo ""
    echo "Applying strings patch..."
    if git apply --check "$SCRIPT_DIR/strings.xml additions.patch" 2>/dev/null; then
        git apply "$SCRIPT_DIR/strings.xml additions.patch"
        echo "✓ Strings patch applied successfully"
    else
        echo "⚠ Strings patch may have conflicts, manual intervention needed"
    fi
fi

echo ""
echo "=========================================="
echo "Patch application complete!"
echo "=========================================="
echo ""
echo "Summary of changes:"
echo "  1. Added 'customOutboundTag' field to RulesetItem DTO"
echo "  2. Added 'custom' option to outbound_tag array"
echo "  3. Added EditText for custom outbound in routing edit UI"
echo "  4. Updated RoutingEditActivity to handle custom outbound selection"
echo "  5. Updated V2rayConfigManager to:"
echo "     - Include custom outbounds in generated config"
echo "     - Support chain proxy (prev/next) for custom group outbounds"
echo ""
echo "Next steps:"
echo "  1. Build the project: ./gradlew assembleDebug"
echo "  2. Test the custom outbound feature in routing settings"
echo ""

#!/bin/bash

COMMIT_HASH="bf4008d327e80e8e8bc1acd8abacc324b35932b8"
PATCH_URL="https://github.com/XTLS/Xray-core/commit/$COMMIT_HASH.patch"



echo "📥 Downloading patch..."
curl -L "$PATCH_URL" -o /tmp/commit.patch

echo "🔧 Applying patch..."
if git apply --check /tmp/commit.patch 2>/dev/null; then
    git apply /tmp/commit.patch
    echo "✅ Patch applied successfully!"
else
    echo "⚠️  Patch has conflicts. Try with --3way:"
    echo "   git apply --3way -v /tmp/commit.patch"
fi

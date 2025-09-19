#!/usr/bin/env bash
set -euo pipefail

# File paths (relative to repository root)
BUILD_GRADLE="V2rayNG/app/build.gradle.kts"
PROGUARD_FILE="V2rayNG/app/proguard-rules.pro"
PERFORMANCE_GRADLE="V2rayNG/gradle.properties"

# Check if files exist
for file in "$BUILD_GRADLE" "$PROGUARD_FILE" "$PERFORMANCE_GRADLE"; do
  if [[ ! -f "$file" ]]; then
    echo "::error file=$file::File not found: $file"
    exit 1
  fi
done

echo "::group::Patching $BUILD_GRADLE"

# ---------- Patch release block with awk ----------
awk -v seen=0 '
/release[[:space:]]*{/ { in_release=1 }
/}/ && in_release {
    if (seen==0) { print "    isShrinkResources = true"; seen=1 }
    in_release=0
}
in_release && /isMinifyEnabled/ { sub(/isMinifyEnabled\s*=\s*false/, "isMinifyEnabled = true") }
{ print }
' "$BUILD_GRADLE" > "$BUILD_GRADLE.tmp" && mv "$BUILD_GRADLE.tmp" "$BUILD_GRADLE"

# ---------- Patch debug block with awk ----------
awk '
/debug[[:space:]]*{/ { in_debug=1 }
in_debug && /isMinifyEnabled/ { sub(/isMinifyEnabled\s*=\s*true/, "isMinifyEnabled = false") }
in_debug && /}/ { in_debug=0 }
{ print }
' "$BUILD_GRADLE" > "$BUILD_GRADLE.tmp" && mv "$BUILD_GRADLE.tmp" "$BUILD_GRADLE"

echo "::endgroup::"

echo "::group::Ensuring R8-safe ProGuard rules"

# ---------- R8-safe ProGuard rules ----------
mkdir -p "$(dirname "$PROGUARD_FILE")"
touch "$PROGUARD_FILE"

PROGUARD_SNIPPET=$(cat <<'EOF'
-dontobfuscate

-keep class ** { *; }
-keep class libv2ray.** { *; }

-keepclasseswithmembernames class * { native <methods>; }
-keepclassmembers class * { static <fields>; static <methods>; }

-keep class * extends android.app.Service { *; }
-keep class * extends android.content.BroadcastReceiver { *; }

-keepattributes Signature,InnerClasses,EnclosingMethod

-dontwarn com.squareup.okhttp.CipherSuite
-dontwarn com.squareup.okhttp.ConnectionSpec
-dontwarn com.squareup.okhttp.TlsVersion
-dontwarn org.bouncycastle.jsse.BCSSLSocket
-dontwarn org.bouncycastle.jsse.provider.BouncyCastleJsseProvider
-dontwarn org.conscrypt.Conscrypt$Version
-dontwarn org.conscrypt.Conscrypt
-dontwarn org.conscrypt.ConscryptHostnameVerifier
-dontwarn org.joda.convert.FromString
-dontwarn org.joda.convert.ToString
-dontwarn org.openjsse.javax.net.ssl.SSLParameters
-dontwarn org.openjsse.javax.net.ssl.SSLSocket
-dontwarn org.openjsse.net.ssl.OpenJSSE
-dontwarn javax.lang.model.element.Modifier
EOF
)

# Ensure LF line endings and append missing lines
TMP_FILE=$(mktemp)
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  line="${line//$'\r'/}"
  # Use -- to prevent grep from interpreting patterns as options
  if ! grep -qxF -- "$line" "$PROGUARD_FILE"; then
    echo "$line" >> "$TMP_FILE"
  fi
done <<< "$PROGUARD_SNIPPET"

# Append existing rules not in snippet to preserve them
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  line="${line//$'\r'/}"
  if ! grep -qxF -- "$line" <<< "$PROGUARD_SNIPPET"; then
    echo "$line" >> "$TMP_FILE"
  fi
done < "$PROGUARD_FILE"

mv "$TMP_FILE" "$PROGUARD_FILE"

echo "::endgroup::"

echo "::group::Ensuring gradle.properties"

# ---------- Gradle properties ----------
mkdir -p "$(dirname "$PERFORMANCE_GRADLE")"
touch "$PERFORMANCE_GRADLE"

declare -A PERFORMANCE_MAP=(
  ["org.gradle.jvmargs"]="-Xmx4g -XX:+UseParallelGC -Dfile.encoding=UTF-8"
  ["org.gradle.parallel"]="true"
  ["org.gradle.caching"]="true"
  ["org.gradle.configureondemand"]="true"
  ["android.enableR8.fullMode"]="true"
  ["kotlin.incremental"]="true"
  ["kotlin.incremental.useClasspathSnapshot"]="true"
  ["android.enableJetifier"]="true"
  ["android.useAndroidX"]="true"
  ["org.gradle.daemon.idletimeout"]="3600000"
  ["org.gradle.vfs.watch"]="true"
)

TMP_FILE=$(mktemp)

while IFS= read -r line || [[ -n "$line" ]]; do
  updated=0
  for key in "${!PERFORMANCE_MAP[@]}"; do
    if [[ "$line" == "$key="* ]]; then
      echo "$key=${PERFORMANCE_MAP[$key]}" >> "$TMP_FILE"
      unset PERFORMANCE_MAP[$key]
      updated=1
      break
    fi
  done
  if [[ $updated -eq 0 ]]; then
    echo "$line" >> "$TMP_FILE"
  fi
done < "$PERFORMANCE_GRADLE"

for key in "${!PERFORMANCE_MAP[@]}"; do
  echo "$key=${PERFORMANCE_MAP[$key]}" >> "$TMP_FILE"
done

mv "$TMP_FILE" "$PERFORMANCE_GRADLE"

echo "::endgroup::"

echo "::group::Changed lines summary"

echo "---- Changed lines in $BUILD_GRADLE ----"
grep -E "isMinifyEnabled|isShrinkResources" "$BUILD_GRADLE" || echo "No matching lines found"

echo "---- ProGuard rules added or present in $PROGUARD_FILE ----"
# Use -- to prevent grep from interpreting patterns as options
grep -E -- "^-dontobfuscate|-keep|-dontwarn" "$PROGUARD_FILE" || echo "No matching rules found"

echo "---- Performance settings in $PERFORMANCE_GRADLE ----"
grep -E "org.gradle.jvmargs|org.gradle.parallel|org.gradle.caching|org.gradle.configureondemand|android.enableR8.fullMode|kotlin.incremental|kotlin.incremental.useClasspathSnapshot|android.enableJetifier|android.useAndroidX|org.gradle.daemon.idletimeout|org.gradle.vfs.watch" "$PERFORMANCE_GRADLE" || echo "No matching settings found"

echo "::endgroup::"

echo "✅ R8-safe ProGuard + performance configs applied."

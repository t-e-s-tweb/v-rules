#!/usr/bin/env bash
set -euo pipefail

BUILD_GRADLE="V2rayNG/app/build.gradle.kts"
PROGUARD_FILE="V2rayNG/app/proguard-rules.pro"
PERFORMANCE_GRADLE="V2rayNG/gradle.properties"

echo "Patching $BUILD_GRADLE..."

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

# ---------- Ensure ProGuard rules ----------
echo "Ensuring ProGuard rules..."
PROGUARD_SNIPPET='
-dontobfuscate

-keep class ** { *; }
-keep class libv2ray.** { *; }

-keepclasseswithmembernames class * {
    native <methods>;
}
-keepclassmembers class * {
    static <fields>;
    static <methods>;
}

-keep class * extends android.app.Service { *; }
-keep class * extends android.content.BroadcastReceiver { *; }

-keepattributes Signature
-keepattributes InnerClasses
-keepattributes EnclosingMethod

-dontwarn com.squareup.okhttp.CipherSuite
-dontwarn com.squareup.okhttp.ConnectionSpec
-dontwarn com.squareup.okhttp.TlsVersion
-dontwarn org.bouncycastle.jsse.BCSSLSocket
-dontwarn org.bouncycastle.jsse.provider.BouncyCastleJsseProvider
-dontwarn org.conscrypt.Conscrypt\$Version
-dontwarn org.conscrypt.Conscrypt
-dontwarn org.conscrypt.ConscryptHostnameVerifier
-dontwarn org.joda.convert.FromString
-dontwarn org.joda.convert.ToString
-dontwarn org.openjsse.javax.net.ssl.SSLParameters
-dontwarn org.openjsse.javax.net.ssl.SSLSocket
-dontwarn org.openjsse.net.ssl.OpenJSSE
'

mkdir -p "$(dirname "$PROGUARD_FILE")"
touch "$PROGUARD_FILE"

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if ! printf '%s\n' "$line" | grep -qxF -f - "$PROGUARD_FILE"; then
    echo "$line" >> "$PROGUARD_FILE"
  fi
done <<< "$PROGUARD_SNIPPET"

# ---------- Gradle properties ----------
echo "Ensuring gradle.properties..."
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

for key in "${!PERFORMANCE_MAP[@]}"; do
  value="${PERFORMANCE_MAP[$key]}"
  if grep -q "^$key=" "$PERFORMANCE_GRADLE"; then
    # macOS sed requires -i '' for in-place edit
    sed -i '' "s|^$key=.*|$key=$value|" "$PERFORMANCE_GRADLE"
  else
    echo "$key=$value" >> "$PERFORMANCE_GRADLE"
  fi
done

# ---------- Print only changed lines ----------
echo
echo "---- Changed lines in $BUILD_GRADLE ----"
grep -E "isMinifyEnabled|isShrinkResources" "$BUILD_GRADLE"

echo
echo "---- ProGuard rules added or present in $PROGUARD_FILE ----"
grep -E "^-dontobfuscate|-keep|-dontwarn" "$PROGUARD_FILE"

echo
echo "---- Performance settings in $PERFORMANCE_GRADLE ----"
grep -E "org.gradle.jvmargs|org.gradle.parallel|org.gradle.caching|org.gradle.configureondemand|android.enableR8.fullMode|kotlin.incremental|kotlin.incremental.useClasspathSnapshot|android.enableJetifier|android.useAndroidX|org.gradle.daemon.idletimeout|org.gradle.vfs.watch" "$PERFORMANCE_GRADLE"

echo
echo "✅ ProGuard + performance configs applied and highlighted above."

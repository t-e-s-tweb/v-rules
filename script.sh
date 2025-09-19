#!/usr/bin/env bash
set -euo pipefail

BUILD_GRADLE="V2rayNG/app/build.gradle.kts"
PROGUARD_FILE="V2rayNG/app/proguard-rules.pro"
PERFORMANCE_GRADLE="V2rayNG/gradle.properties"

# -------- 1. Update build.gradle.kts --------
echo "Patching $BUILD_GRADLE..."

# Set isMinifyEnabled = true in release
sed -i "/release\s*{/,/}/ { \
  s/isMinifyEnabled\s*=\s*false/isMinifyEnabled = true/ \
}" "$BUILD_GRADLE"

# Add isShrinkResources = true if missing in release
if ! sed -n "/release\s*{/,/}/p" "$BUILD_GRADLE" | grep -q "isShrinkResources"; then
  sed -i "/release\s*{/,/}/ { /}/i \    isShrinkResources = true" "$BUILD_GRADLE"
fi

# Ensure debug stays unminified
sed -i "/debug\s*{/,/}/ { \
  s/isMinifyEnabled\s*=\s*true/isMinifyEnabled = false/ \
}" "$BUILD_GRADLE"

# -------- 2. Ensure ProGuard rules safely --------
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

# -------- 3. Update gradle.properties --------
echo "Ensuring gradle.properties..."
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

mkdir -p "$(dirname "$PERFORMANCE_GRADLE")"
touch "$PERFORMANCE_GRADLE"

for key in "${!PERFORMANCE_MAP[@]}"; do
  value="${PERFORMANCE_MAP[$key]}"
  if grep -q "^$key=" "$PERFORMANCE_GRADLE"; then
    sed -i "s|^$key=.*|$key=$value|" "$PERFORMANCE_GRADLE"
  else
    echo "$key=$value" >> "$PERFORMANCE_GRADLE"
  fi
done

# -------- 4. Print patched files --------
echo
echo "---- $BUILD_GRADLE ----"
cat "$BUILD_GRADLE"
echo
echo "---- $PROGUARD_FILE ----"
cat "$PROGUARD_FILE"
echo
echo "---- $PERFORMANCE_GRADLE ----"
cat "$PERFORMANCE_GRADLE"

echo
echo "✅ ProGuard + performance configs applied and displayed above."

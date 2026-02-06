#!/bin/bash

FILE="libxivpn/build.sh"

# 1. Add GOMAXPROCS and GOEXPERIMENT after CGO_ENABLED=1
sed -i '/^export CGO_ENABLED=1$/a\
export GOMAXPROCS=$(nproc)\
export GOEXPERIMENT="runtimefreegc,sizespecializedmalloc,greenteagc,jsonv2,newinliner,heapminimum512kib"' "$FILE"

# 2. Modify CGO_CFLAGS for each architecture
sed -i 's|export CGO_CFLAGS="-target aarch64-linux-android21"|export CGO_CFLAGS="-target aarch64-linux-android21 -O3 -fvisibility=hidden -ffunction-sections -fdata-sections -fomit-frame-pointer"|' "$FILE"
sed -i 's|export CGO_CFLAGS="-target x86_64-linux-android21"|export CGO_CFLAGS="-target x86_64-linux-android21 -O3 -fvisibility=hidden -ffunction-sections -fdata-sections -fomit-frame-pointer"|' "$FILE"
sed -i 's|export CGO_CFLAGS="-target armv7a-linux-androideabi21"|export CGO_CFLAGS="-target armv7a-linux-androideabi21 -O3 -fvisibility=hidden -ffunction-sections -fdata-sections -fomit-frame-pointer"|' "$FILE"

# 3. Add CGO_CXXFLAGS after CGO_LDFLAGS line
sed -i '/^export CGO_LDFLAGS=/a\
export CGO_CXXFLAGS="-O3 -fvisibility=hidden -ffunction-sections -fdata-sections -fomit-frame-pointer"' "$FILE"

# 4. Update CGO_LDFLAGS
sed -i 's|export CGO_LDFLAGS="-v -Wl,-z,max-page-size=16384"|export CGO_LDFLAGS="-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384 -Wl,-z,separate-loadable-segments -Wl,-z,now -Wl,--gc-sections -Wl,--strip-all"|' "$FILE"

# 5. Fix go build: Use proper quoting for -extldflags (double quotes outside, single inside)
#sed -i 's|-ldflags="-s -w -buildid= -linkmode external"|-ldflags="-s -w -buildid= -linkmode=external -extldflags='"'"'-target aarch64-linux-android21 -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384 -Wl,-z,separate-loadable-segments -Wl,-z,now -Wl,--gc-sections -Wl,--strip-all'"'"'"|' "$FILE"
# Replace step 5 with this - remove -extldflags entirely, rely on CGO_LDFLAGS
sed -i 's|-ldflags="-s -w -buildid= -linkmode external"|-ldflags="-s -w -buildid= -linkmode=external"|' "$FILE"

echo "Done patching $FILE"

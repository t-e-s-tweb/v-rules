#!/bin/bash

FILE="libxivpn/build.sh"

# 1. Add GOMAXPROCS and GOEXPERIMENT after CGO_ENABLED=1
sed -i '/^export CGO_ENABLED=1$/a\
export GOMAXPROCS=$(nproc)\
export GOEXPERIMENT="runtimefreegc,sizespecializedmalloc,greenteagc,jsonv2,newinliner,heapminimum512kib"' "$FILE"

# 2. Modify CGO_CFLAGS for each architecture
sed -i 's|export CGO_CFLAGS="-target aarch64-linux-android21"|export CGO_CFLAGS="-target aarch64-linux-android21 -O2 -g -fPIC"|' "$FILE"
sed -i 's|export CGO_CFLAGS="-target x86_64-linux-android21"|export CGO_CFLAGS="-target x86_64-linux-android21 -O2 -g -fPIC"|' "$FILE"
sed -i 's|export CGO_CFLAGS="-target armv7a-linux-androideabi21"|export CGO_CFLAGS="-target armv7a-linux-androideabi21 -O2 -g -fPIC"|' "$FILE"

# 3. Add CGO_CXXFLAGS after CGO_LDFLAGS line
sed -i '/^export CGO_LDFLAGS=/a\
export CGO_CXXFLAGS="-O2 -g -fPIC"' "$FILE"

# 4. Update CGO_LDFLAGS
sed -i 's|export CGO_LDFLAGS="-v -Wl,-z,max-page-size=16384"|export CGO_LDFLAGS="-v -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384"|' "$FILE"

echo "Done patching $FILE"

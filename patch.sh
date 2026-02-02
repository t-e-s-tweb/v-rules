sed -i -e '/export CGO_ENABLED=1/c\
export GOMAXPROCS=$(nproc)\
export CGO_ENABLED=1\
export GOEXPERIMENT="runtimefreegc,sizespecializedmalloc,greenteagc,jsonv2,newinliner,heapminimum512kib"' \
-e '/export CGO_CFLAGS="-target aarch64-linux-android21"/c\
export CGO_CFLAGS="-target aarch64-linux-android21 -O2 -g"' \
-e '/export CGO_CFLAGS="-target x86_64-linux-android21"/c\
export CGO_CFLAGS="-target x86_64-linux-android21 -O2 -g"' \
-e '/export CGO_CFLAGS="-target armv7a-linux-androideabi21"/c\
export CGO_CFLAGS="-target armv7a-linux-androideabi21 -O2 -g"' \
-e '/export CGO_CXXFLAGS=/c\
export CGO_CXXFLAGS="-O2 -g"' \
-e '/export CGO_LDFLAGS=/c\
export CGO_LDFLAGS="-Wl,-z,max-page-size=0x4000 -Wl,-z,common-page-size=0x4000 -Wl,-z,separate-loadable-segments"' libxivpn/build.sh

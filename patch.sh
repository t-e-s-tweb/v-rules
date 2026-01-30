sed -i -e '/export CGO_ENABLED=1/c\
export GOMAXPROCS=$(nproc)\
export CGO_ENABLED=1\
export GOEXPERIMENT="greenteagc,jsonv2,newinliner,regabi,swissmap,heapminimum512kib"' \
-e '/export CGO_CFLAGS="-target aarch64-linux-android21"/c\
export CGO_CFLAGS="-target aarch64-linux-android21 -O3 -flto=thin -fomit-frame-pointer -ffunction-sections -fdata-sections"' \
-e '/export CGO_CFLAGS="-target x86_64-linux-android21"/c\
export CGO_CFLAGS="-target x86_64-linux-android21 -O3 -flto=thin -fomit-frame-pointer -ffunction-sections -fdata-sections"' \
-e '/export CGO_CFLAGS="-target armv7a-linux-androideabi21"/c\
export CGO_CFLAGS="-target armv7a-linux-androideabi21 -O3 -flto=thin -fomit-frame-pointer -ffunction-sections -fdata-sections"' \
-e '/export CGO_CXXFLAGS=/c\
export CGO_CXXFLAGS="-O3 -flto=thin -fomit-frame-pointer -ffunction-sections -fdata-sections"' \
-e '/export CGO_LDFLAGS=/c\
export CGO_LDFLAGS="-O3 -flto=thin -fuse-ld=lld -Wl,-z,max-page-size=16384"' libxivpn/build.sh

#!/bin/bash
set -euo pipefail
workspace=$(cd -- "${1:?graphics workspace}" && pwd)
recipe=$(cd -- "${BASH_SOURCE[0]%/*}" && pwd)
[[ $(git -C "$workspace/aquamarine" rev-parse HEAD) == "a79fb21b2e2a82dd061a6d071802bcf38bd5c383" ]]
cmp <(git -C "$workspace/aquamarine" diff) "$recipe/aquamarine-software-egl.patch"
[[ $(/usr/bin/clang --version | head -1) == "clang version 22.1.8" ]]
export PKG_CONFIG_SYSROOT_DIR="$workspace/sysroot"
export PKG_CONFIG_LIBDIR="$workspace/sysroot/usr/lib/pkgconfig:$workspace/sysroot/usr/share/pkgconfig"
export QEMU_LD_PREFIX="$workspace/sysroot"
export PATH="$recipe/host-tools:$PATH"
/usr/bin/cmake -S "$workspace/aquamarine" -B "$workspace/build-native" -G Ninja \
  --toolchain "$recipe/aarch64-toolchain.cmake" \
  -DOMARCHY_GRAPHICS_WORKSPACE="$workspace" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr -DBUILD_TESTING=OFF
/usr/bin/cmake --build "$workspace/build-native" --parallel "${OMARCHY_BUILD_JOBS:-2}"

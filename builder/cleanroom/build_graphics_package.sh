#!/bin/bash
# Package the verified cross-compiled library in a disposable native builder.
set -euo pipefail
stage=${1:?staged ARM64 graphics package directory}
output=${2:?package output directory}
recipe=${BASH_SOURCE[0]%/*}/graphics/PKGBUILD
work=$(mktemp -d /tmp/omarchy-graphics-package.XXXXXX)
trap 'rm -rf "$work"' EXIT
cp /etc/makepkg.conf "$work/makepkg.conf"
sed -i 's/^CARCH=.*/CARCH="aarch64"/; s/^CHOST=.*/CHOST="aarch64-unknown-linux-gnu"/' "$work/makepkg.conf"
useradd -m -u 1000 builder
cp "$recipe" "$work/PKGBUILD"
chown -R builder:builder "$work"
cd "$work"
runuser -u builder -- env OMARCHY_GRAPHICS_STAGE="$stage" PKGDEST="$work" \
  makepkg --config "$work/makepkg.conf" --nodeps --noconfirm
for package in "$work/"*.pkg.tar.zst; do
  destination="$output/${package##*/}"
  [[ ! -e $destination && ! -L $destination ]] || exit 1
  install -m 0644 -o "${HOST_UID:?}" -g "${HOST_GID:?}" "$package" "$destination"
done

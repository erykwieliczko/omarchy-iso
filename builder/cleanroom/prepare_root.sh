#!/bin/bash
# Build only disposable image files; never discover or accept a physical disk.
set -euo pipefail

input=${1:?input artifact directory}
base=${2:?verified base image directory}
output=${3:?new output directory}
release=$(cat "$input/kernel/kernel.release")
root_uuid=4f4d5801-524f-4f54-8713-000000000001
kernel_package=linux-omarchy-j713-7.1.9.j713-4-aarch64.pkg.tar.zst
graphics_package=aquamarine-0.14.0-3-aarch64.pkg.tar.zst

fail() { echo "cleanroom-root: $*" >&2; exit 1; }
[[ ! -e $output && ! -L $output ]] || fail "output already exists"
[[ -f $input/$kernel_package && -d $input/firmware ]] || fail "missing admitted kernel or firmware"
for name in root.img boot.img; do
  [[ -f $base/$name && ! -L $base/$name ]] || fail "base image is unsafe"
  expected=$(cat "$base/$name.sha256")
  [[ $expected =~ ^[0-9a-f]{64}$ ]] || fail "invalid base image digest"
  printf '%s  %s\n' "$expected" "$base/$name" | sha256sum --check --status - \
    || fail "base image changed after admission"
done
python3 "${BASH_SOURCE[0]%/*}/verify_inputs.py" "$input"
mkdir -p "$output"
cp --reflink=auto --sparse=always "$base/root.img" "$output/root.img"
cp --reflink=auto --sparse=always "$base/boot.img" "$output/boot.img"
cp "$base/omarchy-volume.icns" "$output/omarchy-volume.icns"

for index in {0..63}; do
  [[ -e /dev/loop$index ]] || mknod "/dev/loop$index" b 7 "$index"
done
loops=()
top=$(mktemp -d /tmp/omarchy-image-top.XXXXXX)
target=$(mktemp -d /tmp/omarchy-image-target.XXXXXX)
cleanup() {
  local status=$?
  set +e
  mountpoint -q "$target" && umount -R "$target"
  mountpoint -q "$top" && umount "$top"
  for loop in "${loops[@]}"; do losetup -d "$loop"; done
  rmdir "$target" "$top"
  exit "$status"
}
trap cleanup EXIT
root_loop=$(losetup --find --show "$output/root.img")
loops+=("$root_loop")
boot_loop=$(losetup --find --show "$output/boot.img")
loops+=("$boot_loop")
btrfstune -f -U "$root_uuid" "$root_loop"
mount "$root_loop" "$top"
[[ -d $top/@ && -d $top/@home && -d $top/@pkg && -d $top/@log ]] \
  || fail "base subvolume layout changed"
if [[ -d $top/@factory ]]; then btrfs subvolume delete "$top/@factory"; fi
mount -o subvol=@,compress=zstd "$root_loop" "$target"
mount "$boot_loop" "$target/boot"
for entry in 'home:@home' 'var/log:@log' 'var/cache/pacman/pkg:@pkg'; do
  mount -o "subvol=${entry#*:},compress=zstd" "$root_loop" "$target/${entry%:*}"
done

# Stock package removal uses pacman's dependency and ownership database. The
# model-specific kernel package owns its modules and blocks stock boot writers.
arch-chroot "$target" pacman --noconfirm -R \
  asahi-fwextract asahi-scripts linux-asahi linux-asahi-headers m1n1 uboot-asahi grub
[[ ! -e $target/usr/bin/update-m1n1 ]] || fail "stock boot writer remains"

# The source release's first-boot vendor firmware importer remains available;
# built-in J713 drivers additionally need these files in the early initramfs.
while IFS= read -r -d '' file; do
  relative=${file#"$input/firmware/"}
  install -Dm0644 "$file" "$target/usr/lib/firmware/$relative"
done < <(find "$input/firmware/apple" "$input/firmware/brcm" -type f -print0)
mkdir -p "$target/etc/mkinitcpio.conf.d"
rm -f "$target/etc/mkinitcpio.conf.d/90-omarchy-asahi.conf"
cat > "$target/etc/mkinitcpio.conf.d/95-omarchy-cleanroom.conf" <<'CONFIG'
MODULES=(apple_pmp_thermal)
HOOKS=(base systemd modconf keyboard sd-vconsole block filesystems fsck)
FILES=(
  /usr/lib/firmware/apple/tpmtfw-j713.bin
  /usr/lib/firmware/brcm/brcmfmac4388c2-pcie.apple,garden.bin
  /usr/lib/firmware/brcm/brcmfmac4388c2-pcie.apple,garden.sig
  /usr/lib/firmware/brcm/brcmfmac4388c2-pcie.apple,garden.clm_blob
  /usr/lib/firmware/brcm/brcmfmac4388c2-pcie.apple,garden.txcap_blob
  /usr/lib/firmware/brcm/brcmfmac4388c2-pcie.apple,garden-WLMT-u.txt
  /usr/lib/firmware/brcm/brcmfmac4388c2-pcie.apple,garden-WLMT-a.txt
  /usr/lib/firmware/regulatory.db
  /usr/lib/firmware/regulatory.db.p7s
)
COMPRESSION=zstd
CONFIG
cp "$input/$kernel_package" "$target/var/tmp/$kernel_package"
arch-chroot "$target" pacman --noconfirm -U "/var/tmp/$kernel_package"
rm "$target/var/tmp/$kernel_package"
[[ -f $target/usr/lib/modules/$release/kernel/drivers/thermal/apple-pmp-thermal.ko ]] \
  || fail "matching thermal module is missing"
arch-chroot "$target" depmod "$release"
arch-chroot "$target" mkinitcpio -k "$release" -g /boot/initramfs-linux-omarchy-j713.img
sed -i "s/4f4d5801-524f-4f54-8000-000000000001/$root_uuid/g" "$target/etc/fstab"

# Software EGL support applies to both the SDDM greeter and the uwsm session.
cp "$input/$graphics_package" "$target/var/tmp/$graphics_package"
arch-chroot "$target" pacman --noconfirm -U "/var/tmp/$graphics_package"
rm "$target/var/tmp/$graphics_package"
install -Dm0644 "${BASH_SOURCE[0]%/*}/config/software-rendering.conf" \
  "$target/etc/environment.d/90-omarchy-j713-rendering.conf"
install -Dm0644 "${BASH_SOURCE[0]%/*}/config/sddm-software-rendering.conf" \
  "$target/etc/systemd/system/sddm.service.d/90-omarchy-j713-rendering.conf"
[[ -f $target/usr/local/share/wayland-sessions/omarchy.desktop ]] \
  || fail "Omarchy graphical session is missing"
[[ -L $target/etc/systemd/system/display-manager.service ]] \
  || fail "graphical login is not enabled"
# J713 has no supported internal-speaker driver or protection profile. Keep the
# daemon masked; never substitute a fake protection profile to make it start.
arch-chroot "$target" systemctl mask speakersafetyd.service

mkdir -p "$target/usr/share/omarchy/cleanroom"
install -m0644 "$input/j713-boot-inputs.json" "$target/usr/share/omarchy/cleanroom/boot-inputs.json"
arch-chroot "$target" pacman -Q > "$output/installed-packages.txt"
cp "$target/boot/initramfs-linux-omarchy-j713.img" "$output/initramfs.img"
cp "$target/etc/fstab" "$output/fstab"
cp "$target/etc/mkinitcpio.conf.d/95-omarchy-cleanroom.conf" "$output/mkinitcpio.conf"
[[ -f $target/var/lib/omarchy/provisioning/pending ]] || fail "first-boot setup is missing"
[[ -L $target/etc/systemd/system/multi-user.target.wants/omarchy-provision-owner.service ]] \
  || fail "first-boot setup is not enabled"
[[ -L $target/etc/systemd/system/multi-user.target.wants/NetworkManager.service ]] \
  || fail "network setup is not enabled"

# Recreate the factory snapshot from this variant, without retaining the old
# kernel or a user-specific machine identity in its rollback image.
: > "$target/etc/machine-id"
rm -f "$target/var/lib/systemd/random-seed" "$target/etc/ssh/ssh_host_"*
sync
btrfs subvolume snapshot "$top/@" "$top/@factory"
btrfs property set -ts "$top/@factory" ro true
umount -R "$target"
umount "$top"
for loop in "${loops[@]}"; do losetup -d "$loop"; done
loops=()
fallocate --dig-holes "$output/root.img"
fallocate --dig-holes "$output/boot.img"
printf '%s\n' "$root_uuid" > "$output/root-uuid"

chown -R "${HOST_UID:?}:${HOST_GID:?}" "$output"

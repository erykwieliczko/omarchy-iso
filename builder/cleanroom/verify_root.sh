#!/bin/bash
# Read-only verification of disposable filesystem images.
set -euo pipefail
input=${1:?artifact directory}
images=${2:?built image directory}
output=${3:?new verification directory}
release=$(cat "$input/kernel/kernel.release")
python3 "${BASH_SOURCE[0]%/*}/verify_inputs.py" "$input"
[[ ! -e $output ]] || exit 1
mkdir -p "$output"
for index in {0..63}; do
  [[ -e /dev/loop$index ]] || mknod "/dev/loop$index" b 7 "$index"
done
root_loop=$(losetup --find --show --read-only "$images/root.img")
boot_loop=$(losetup --find --show --read-only "$images/boot.img")
target=$(mktemp -d)
cleanup() {
  local status=$?
  set +e
  mountpoint -q "$target/boot" && umount "$target/boot"
  mountpoint -q "$target" && umount "$target"
  losetup -d "$root_loop" "$boot_loop"
  rmdir "$target"
  exit "$status"
}
trap cleanup EXIT
mount -o ro,subvol=@ "$root_loop" "$target"
mount -o ro "$boot_loop" "$target/boot"
cmp "$images/initramfs.img" "$target/boot/initramfs-linux-omarchy-j713.img"
python3 "${BASH_SOURCE[0]%/*}/verify_initramfs.py" "$images/initramfs.img" "$input/firmware" "$input/kernel/lib/modules/$release/kernel/drivers/thermal/apple-pmp-thermal.ko" > "$output/initramfs.txt"
[[ $(blkid -s UUID -o value "$root_loop") == "4f4d5801-524f-4f54-8713-000000000001" ]]
[[ ! -s $target/etc/machine-id ]]
[[ ! -e $target/usr/bin/update-m1n1 ]]
[[ -f $target/var/lib/omarchy/provisioning/pending ]]
[[ -L $target/etc/systemd/system/multi-user.target.wants/omarchy-provision-owner.service ]]
[[ -L $target/etc/systemd/system/multi-user.target.wants/omarchy-vendor-firmware.service ]]
[[ -L $target/etc/systemd/system/multi-user.target.wants/NetworkManager.service ]]
cmp "${BASH_SOURCE[0]%/*}/config/software-rendering.conf" \
  "$target/etc/environment.d/90-omarchy-j713-rendering.conf"
cmp "${BASH_SOURCE[0]%/*}/config/sddm-software-rendering.conf" \
  "$target/etc/systemd/system/sddm.service.d/90-omarchy-j713-rendering.conf"
[[ -f $target/usr/local/share/wayland-sessions/omarchy.desktop ]]
[[ -L $target/etc/systemd/system/display-manager.service ]]
[[ $(readlink "$target/etc/systemd/system/speakersafetyd.service") == "/dev/null" ]]
[[ -z $(find "$target/usr/lib/modules" -type d ! -perm 0755 -print -quit) ]]
[[ -z $(find "$target/usr/lib/modules" -type f ! -perm 0644 -print -quit) ]]
while IFS= read -r -d '' file; do
  relative=${file#"$input/kernel/lib/modules/"}
  cmp "$file" "$target/usr/lib/modules/$relative"
done < <(find "$input/kernel/lib/modules" -type f -name '*.ko' -print0)
cmp "$input/kernel/build-receipt.json" "$target/usr/share/omarchy/kernel/build-receipt.json"
modprobe -d "$target" -S "$release" --show-depends nf_tables > "$output/nftables-modules.txt"
cmp "$input/kernel/Image" "$target/usr/lib/modules/$release/vmlinuz"
cmp "$input/kernel/config" "$target/usr/lib/modules/$release/config"
modinfo "$target/usr/lib/modules/$release/kernel/drivers/thermal/apple-pmp-thermal.ko" > "$output/thermal-module.txt"
[[ $(cat "$target/etc/modules-load.d/omarchy-j713-thermal.conf") == "apple-pmp-thermal" ]]
while IFS= read -r -d '' file; do
  relative=${file#"$input/firmware/"}
  cmp "$file" "$target/usr/lib/firmware/$relative"
done < <(find "$input/firmware/apple" "$input/firmware/brcm" -type f -print0)
cp "$target/etc/fstab" "$output/fstab"
cp "$target/etc/systemd/system/omarchy-provision-owner.service" "$output/"
cp "$target/etc/systemd/system/omarchy-vendor-firmware.service" "$output/"
python3 - "$images/installed-packages.txt" <<'PY'
import sys
from pathlib import Path
packages=dict(line.split(' ',1) for line in Path(sys.argv[1]).read_text().splitlines())
assert packages['linux-omarchy-j713']=='7.1.9.j713-4'
assert packages['aquamarine']=='0.14.0-3'
assert {'omarchy-dev','omarchy-settings-dev','mkinitcpio','systemd','networkmanager'} <= packages.keys()
assert not {'asahi-fwextract','asahi-scripts','linux-asahi','linux-asahi-headers','m1n1','uboot-asahi','grub'} & packages.keys()
PY
python3 - "$images" "$output" <<'PY'
import hashlib,json,sys
from pathlib import Path
images,output=map(Path,sys.argv[1:])
records={}
for name in ('root.img','boot.img','initramfs.img'):
    digest=hashlib.sha256()
    with (images/name).open('rb') as reader:
        while chunk:=reader.read(4*1024*1024): digest.update(chunk)
    records[name]={'size_bytes':(images/name).stat().st_size,'sha256':digest.hexdigest()}
(output/'verification.json').write_text(json.dumps(records,indent=2)+'\n')
PY
printf 'passed\n' > "$output/result"
chown -R "${HOST_UID:?}:${HOST_GID:?}" "$output"

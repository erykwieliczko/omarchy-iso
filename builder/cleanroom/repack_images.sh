#!/bin/bash
# Copy only live files into newly formatted, initially zeroed image files.
set -euo pipefail
input=${1:?sanitized image directory}
output=${2:?new output directory}
[[ ! -e $output && ! -L $output ]] || exit 1
for name in root.img boot.img; do
  [[ -f $input/$name && ! -L $input/$name ]] || exit 1
done
mkdir "$output"
work=$(mktemp -d /tmp/omarchy-repack.XXXXXX)
loops=()
mounts=()
cleanup() {
  local status=$?
  set +e
  for (( i=${#mounts[@]}-1; i>=0; i-- )); do umount "${mounts[i]}"; done
  for loop in "${loops[@]}"; do losetup -d "$loop"; done
  # A failed unmount must never turn cleanup into recursive deletion inside a
  # mounted filesystem. Leave nonempty or still-mounted directories for review.
  for name in old-root old-boot new-root new-boot; do
    mountpoint -q "$work/$name" || rmdir "$work/$name"
  done
  rmdir "$work"
  exit "$status"
}
trap cleanup EXIT
for name in old-root old-boot new-root new-boot; do mkdir "$work/$name"; done
old_root=$(losetup --find --show --read-only "$input/root.img")
loops+=("$old_root")
old_boot=$(losetup --find --show --read-only "$input/boot.img")
loops+=("$old_boot")
root_uuid=$(blkid -s UUID -o value "$old_root")
boot_uuid=$(blkid -s UUID -o value "$old_boot")
mount -o ro,subvolid=5 "$old_root" "$work/old-root"
mounts+=("$work/old-root")
mount -o ro "$old_boot" "$work/old-boot"
mounts+=("$work/old-boot")
truncate -s "$(stat -c %s "$input/root.img")" "$output/root.img"
truncate -s "$(stat -c %s "$input/boot.img")" "$output/boot.img"
new_root=$(losetup --find --show "$output/root.img")
loops+=("$new_root")
new_boot=$(losetup --find --show "$output/boot.img")
loops+=("$new_boot")
# Use temporary UUIDs while source filesystems with the desired UUIDs exist.
mkfs.btrfs -f "$new_root"
mkfs.ext4 -F -E lazy_itable_init=0,lazy_journal_init=0 "$new_boot"
mount -o compress=zstd "$new_root" "$work/new-root"
mounts+=("$work/new-root")
mount "$new_boot" "$work/new-boot"
mounts+=("$work/new-boot")
for subvolume in @ @home @pkg @log; do
  [[ -d $work/old-root/$subvolume && ! -L $work/old-root/$subvolume ]]
  btrfs subvolume create "$work/new-root/$subvolume"
  cp -a --reflink=never "$work/old-root/$subvolume/." "$work/new-root/$subvolume/"
done
cp -a --reflink=never "$work/old-boot/." "$work/new-boot/"
btrfs subvolume snapshot -r "$work/new-root/@" "$work/new-root/@factory"
sync
for (( i=${#mounts[@]}-1; i>=0; i-- )); do umount "${mounts[i]}"; done
mounts=()
losetup -d "$old_root" "$old_boot"
loops=("$new_root" "$new_boot")
btrfstune -f -U "$root_uuid" "$new_root"
tune2fs -U "$boot_uuid" "$new_boot"
for loop in "${loops[@]}"; do losetup -d "$loop"; done
loops=()
python3 - "$output" <<'PY'
import hashlib, json, sys
from pathlib import Path
output = Path(sys.argv[1])
records = {}
for name in ('root.img', 'boot.img'):
    with (output / name).open('rb') as reader:
        records[name] = hashlib.file_digest(reader, 'sha256').hexdigest()
(output / 'fresh-filesystems.json').write_text(json.dumps(records, indent=2) + '\n')
PY

# SPDX-License-Identifier: MIT
"""Build the model boot bundle; no device or user paths are embedded."""
import argparse
import gzip
import shutil
import struct
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

from verify_inputs import verify


def kernel_command_line(root_uuid, model="j713"):
    if str(uuid.UUID(root_uuid)) != root_uuid:
        raise ValueError('invalid root image UUID')
    if model not in ("j713", "j700"):
        raise ValueError("unknown boot model")
    return (
        'console=tty0 console=ttySAC0,115200 quiet loglevel=3 nohlt nokaslr '
        'clocksource.arm_arch_timer.evtstrm=0 iommu.passthrough=1 clk_ignore_unused '
        'pd_ignore_unused efi=noruntime panic=0 root=UUID=' + root_uuid
        + ' rootflags=subvol=@ rw systemd.unit=graphical.target firmware_class.path=/vendorfw'
        + (' idle=nop arm64.nowfxt' if model == 'j700' else '')
    )


def disk_payload(stage2, dtbs, uboot):
    if len(uboot) < 64 or uboot[56:60] != b'ARM\x64':
        raise ValueError('U-Boot is not an ARM64 Image')
    size = struct.unpack_from('<Q', uboot, 16)[0]
    if not len(uboot) <= size <= 64 * 1024**2:
        raise ValueError('invalid U-Boot ARM64 Image size')
    for dtb in dtbs:
        if len(dtb) < 40 or dtb[:4] != b'\xd0\x0d\xfe\xed':
            raise ValueError('invalid boot DTB')
        if struct.unpack_from('>I', dtb, 4)[0] != len(dtb):
            raise ValueError('boot DTB size mismatch')
    # Stage1 supplies chosen variables and their terminator at runtime. An
    # earlier zero terminator here would hide the installation's ESP UUID.
    return stage2 + b''.join(dtbs) + gzip.compress(uboot.ljust(size, b'\x00'), mtime=0)


def build(inputs, images, grub_build, enablement, output):
    verify(inputs)
    root_uuid = (images / 'root-uuid').read_text().strip()
    output.mkdir(exist_ok=False)
    boot = disk_payload((inputs / 'm1n1-stage2.bin').read_bytes(),
                        [(inputs / name).read_bytes() for name in ('kernel/t8132-j713.dtb', 'j700.dtb')],
                        (inputs / 'u-boot.bin').read_bytes())
    receipt = {}
    for model in ('j713', 'j700'):
        target = output / model
        target.mkdir()
        configuration = (
            "set timeout=3\nset default=0\n"
            "if ! regexp --set=1:omarchy_esp '^\\(([^)]+)\\)' \"$cmdpath\"; then\n"
            "  echo 'Cannot identify the Omarchy EFI partition'; sleep --interruptible 30; halt\nfi\n"
            "menuentry 'Omarchy' {\n"
            '  linux ($omarchy_esp)/omarchy/Image ' + kernel_command_line(root_uuid, model)
            + '\n  initrd ($omarchy_esp)/omarchy/initramfs.img ($omarchy_esp)/vendorfw/firmware.cpio\n}\n'
        )
        (target / 'grub.cfg').write_text(configuration)
        subprocess.run([
            str(grub_build / 'grub-mkstandalone'), '-O', 'arm64-efi',
            '-d', str(grub_build / 'grub-core'),
            '--modules=normal configfile linux part_gpt btrfs fat regexp test sleep halt echo cat',
            '--locales=', '--fonts=', '-o', str(target / 'BOOTAA64.EFI'),
            'boot/grub/grub.cfg=' + str(target / 'grub.cfg'),
        ], check=True)
        if not 0 < (target / 'BOOTAA64.EFI').stat().st_size <= 64 * 1024**2:
            raise ValueError('EFI executable exceeds the Neo load buffer')
        (target / 'boot.bin').write_bytes(boot)
        shutil.copyfile(inputs / 'kernel/Image', target / 'Image')
        shutil.copyfile(images / 'initramfs.img', target / 'initramfs.img')
        for path in target.iterdir():
            receipt[path.relative_to(output).as_posix()] = {
                'size_bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'images', 'grub_build', 'enablement', 'output'):
        parser.add_argument(name, type=Path)
    print(json.dumps(build(**vars(parser.parse_args())), indent=2))

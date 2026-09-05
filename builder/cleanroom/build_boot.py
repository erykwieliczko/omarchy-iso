# SPDX-License-Identifier: MIT
"""Build the model boot bundle; no device or user paths are embedded."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

from verify_inputs import verify


def kernel_command_line(root_uuid):
    if str(uuid.UUID(root_uuid)) != root_uuid:
        raise ValueError('invalid root image UUID')
    return (
        'console=tty0 console=ttySAC0,115200 loglevel=3 nohlt nokaslr '
        'clocksource.arm_arch_timer.evtstrm=0 iommu.passthrough=1 clk_ignore_unused '
        'pd_ignore_unused efi=noruntime panic=0 root=UUID=' + root_uuid
        + ' rootflags=subvol=@ rw systemd.unit=graphical.target'
    )


def build(inputs, images, grub_build, enablement, output):
    verify(inputs)
    root_uuid = (images / 'root-uuid').read_text().strip()
    if str(uuid.UUID(root_uuid)) != root_uuid:
        raise ValueError('invalid root image UUID')
    output.mkdir(exist_ok=False)
    command_line = kernel_command_line(root_uuid)
    configuration = (
        "set timeout=3\nset default=0\nmenuentry 'Omarchy M4 — first boot' {\n"
        '  linux (memdisk)/boot/Image ' + command_line
        + '\n  initrd (memdisk)/boot/initramfs.cpio\n}\n'
    )
    (output / 'grub.cfg').write_text(configuration)
    subprocess.run([
        str(grub_build / 'grub-mkstandalone'), '-O', 'arm64-efi',
        '-d', str(grub_build / 'grub-core'),
        '--modules=normal configfile linux part_gpt btrfs search search_fs_uuid echo cat',
        '--locales=', '--fonts=', '-o', str(output / 'BOOTAA64.EFI'),
        'boot/grub/grub.cfg=' + str(output / 'grub.cfg'),
        'boot/Image=' + str(inputs / 'kernel/Image'),
        'boot/initramfs.cpio=' + str(images / 'initramfs.img'),
    ], check=True)
    subprocess.run([
        '/bin/bash', str(enablement / 'build_chainload.sh'), '--disk-boot',
        '--m1n1', str(inputs / 'm1n1-stage2.bin'),
        '--dtb', str(inputs / 'kernel/t8132-j713.dtb'),
        '--u-boot', str(inputs / 'u-boot.bin'),
        '--efi', str(output / 'BOOTAA64.EFI'), '--output', str(output / 'boot.bin'),
    ], check=True)
    receipt = {
        path.name: {'size_bytes': path.stat().st_size,
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in output.iterdir() if path.is_file()
    }
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'images', 'grub_build', 'enablement', 'output'):
        parser.add_argument(name, type=Path)
    print(json.dumps(build(**vars(parser.parse_args())), indent=2))

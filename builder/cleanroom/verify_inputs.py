"""Check every admitted cleanroom payload input before image mutation."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

from verify_kernel import verify_artifacts
from build_u_boot import BOOTCOMMAND


def verify(directory):
    manifest = json.loads((directory / "j713-boot-inputs.json").read_text())
    if (manifest["schema_version"] != 1 or manifest["profile"]["device_identifier"] != "apple,j713"
            or manifest["profile"]["boot_format"] != "m1n1-uboot-grub-apple-download-v2"):
        raise ValueError("unsupported cleanroom payload input")
    required = {"kernel/Image", "kernel/config", "kernel/t8132-j713.dtb", "m1n1-stage2.bin", "u-boot.bin",
                "kernel/kernel.release", "kernel/build-receipt.json", "u-boot.config", "u-boot-receipt.json",
                "linux-omarchy-j713-7.1.9.j713-4-aarch64.pkg.tar.zst",
                "aquamarine-0.14.0-3-aarch64.pkg.tar.zst"}
    if not required.issubset(manifest["artifacts"]):
        raise ValueError("incomplete cleanroom artifact set")
    if any(name == 'apple-restore.zip' or name.startswith(('firmware/apple/', 'firmware/brcm/'))
           for name in manifest['artifacts']):
        raise ValueError('firmware-free recipe cannot admit vendor firmware inputs')
    for name, expected in manifest["artifacts"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
            raise ValueError("unsafe cleanroom artifact name")
        path = directory / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size != expected["size_bytes"]:
            raise ValueError("cleanroom artifact file type or size changed: " + name)
        digest = hashlib.sha256()
        with path.open("rb") as reader:
            while chunk := reader.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected["sha256"]:
            raise ValueError("cleanroom artifact digest changed: " + name)
    boot = json.loads((directory / 'u-boot-receipt.json').read_text())
    if (boot['source_revision'] != manifest['profile']['sources']['u_boot']
            or boot['boot_mode'] != 'uuid-bound-esp'
            or any(boot['artifacts'][name] != manifest['artifacts'][name]
                   for name in ('u-boot.bin', 'u-boot.config'))):
        raise ValueError('U-Boot build receipt does not match admitted disk loader')
    config = (directory / 'u-boot.config').read_text().splitlines()
    if not {'# CONFIG_APPLE_PRELOADED_EFI is not set', 'CONFIG_ENV_IS_NOWHERE=y',
            'CONFIG_BOOTCOMMAND="' + BOOTCOMMAND + '"'} <= set(config):
        raise ValueError('U-Boot does not load the UUID-bound ESP')
    if 'CONFIG_EXTRA_FIRMWARE=""' not in (directory / 'kernel/config').read_text().splitlines():
        raise ValueError('kernel may contain built-in vendor firmware')
    verify_artifacts(directory / "kernel")
    return manifest


if __name__ == "__main__":
    verify(Path(sys.argv[1]))

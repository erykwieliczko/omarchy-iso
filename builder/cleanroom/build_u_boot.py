"""Build the pinned U-Boot with UUID-bound disk EFI loading."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


REVISION = '7af6b444d69a291ea697f6f80591f75eec5ef7ff'
BOOTCOMMAND = 'load nvme ${fw_dev_part} ${loadaddr} /EFI/BOOT/BOOTAA64.EFI && bootefi ${loadaddr} ${fdtcontroladdr}'


def build(checkout, output):
    output.mkdir(exist_ok=False)
    source, build = output / 'source', output / 'build'
    source.mkdir()
    build.mkdir()
    archive = output / 'source.tar'
    with archive.open('xb') as writer:
        subprocess.run(['git', '-c', 'safe.directory=' + str(checkout), '-C', str(checkout),
                        'archive', REVISION], stdout=writer, check=True)
    with tarfile.open(archive) as reader:
        reader.extractall(source, filter='data')
    archive.unlink()
    config = Path(__file__).parent / 'bootloader/u-boot.config'
    shutil.copyfile(config, build / '.config')
    env = os.environ | {'SOURCE_DATE_EPOCH': '1788566400', 'KBUILD_BUILD_USER': 'builder',
                        'KBUILD_BUILD_HOST': 'omarchy'}
    command = ['make', '-C', str(source), 'O=' + str(build), 'CROSS_COMPILE=aarch64-linux-gnu-']
    subprocess.run(command + ['olddefconfig'], env=env, check=True)
    actual = (build / '.config').read_text()
    required = ['# CONFIG_APPLE_PRELOADED_EFI is not set', 'CONFIG_ENV_IS_NOWHERE=y',
                'CONFIG_BOOTCOMMAND="' + BOOTCOMMAND + '"', 'CONFIG_FS_FAT=y', 'CONFIG_CMD_NVME=y']
    if not all(line in actual.splitlines() for line in required):
        raise ValueError('U-Boot disk EFI configuration changed')
    subprocess.run(command + ['-j' + os.environ.get('OMARCHY_BUILD_JOBS', '10')], env=env, check=True)
    for name in ('u-boot.bin', '.config'):
        shutil.copyfile(build / name, output / ('u-boot.config' if name == '.config' else name))
    receipt = {'source_revision': REVISION, 'boot_mode': 'uuid-bound-esp', 'artifacts': {}}
    for name in ('u-boot.bin', 'u-boot.config'):
        path = output / name
        receipt['artifacts'][name] = {'size_bytes': path.stat().st_size,
                                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (output / 'u-boot-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.checkout.resolve(), args.output.resolve())

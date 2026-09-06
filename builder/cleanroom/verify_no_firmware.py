"""Audit all live subvolumes and boot files before firmware-free publication."""
from pathlib import Path
import sys


def verify(top, boot):
    expected = {'@', '@home', '@pkg', '@log', '@factory'}
    if {p.name for p in top.iterdir()} != expected:
        raise ValueError('unexpected root image subvolume inventory')
    for volume in ('@', '@factory'):
        root = top / volume
        firmware = root / 'usr/lib/firmware'
        if {p.name for p in firmware.iterdir()} != {'regulatory.db', 'regulatory.db.p7s'}:
            raise ValueError('vendor firmware remains in ' + volume)
        for p in firmware.iterdir():
            if p.is_symlink() or not p.is_file():
                raise ValueError('unsafe regulatory database input')
        packages = root / 'var/lib/pacman/local'
        if any(p.name.startswith('linux-firmware-') for p in packages.iterdir()):
            raise ValueError('vendor firmware package remains in ' + volume)
    if any(p.is_file() or p.is_symlink() for p in (top / '@pkg').rglob('*')):
        raise ValueError('package cache must contain no files in firmware-free image')
    for base in (top, boot):
        for p in base.rglob('*'):
            if p.is_symlink() or not p.is_file():
                continue
            name = p.name.lower()
            if (name.endswith(('.im4p', '.ipsw', '.dmg.aea', '.trx', '.clmb', '.txcb'))
                    or name in ('apple-restore.zip', 'firmware.tar', 'firmware.cpio', 'tpmtfw-j713.bin')
                    or name.startswith('brcmfmac4388') or '.pkg.tar.' in name):
                raise ValueError('possible retained vendor firmware or package archive: ' + str(p))
    print('all subvolumes and boot files: no vendor firmware or cached packages')


if __name__ == '__main__':
    verify(*map(Path, sys.argv[1:]))

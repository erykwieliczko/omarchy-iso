"""Read mkinitcpio's early CPIO plus zstd archive without executing guest code."""
import hashlib
from pathlib import Path
import subprocess
import sys

image, firmware, thermal = map(Path, sys.argv[1:])
data = image.read_bytes()
offset = data.find(b'\x28\xb5\x2f\xfd', 0, 8 * 1024 * 1024)
if offset < 0:
    raise ValueError('missing zstd initramfs stream')
data = subprocess.run(['zstd', '-d', '-c'], input=data[offset:], capture_output=True, check=True).stdout
members = {}
offset = 0
while offset + 110 <= len(data):
    header = data[offset:offset + 110]
    if header[:6] != b'070701':
        raise ValueError('invalid newc initramfs')
    fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
    size, namesize = fields[6], fields[11]
    name = data[offset + 110:offset + 110 + namesize - 1].decode()
    offset = (offset + 110 + namesize + 3) & ~3
    body = data[offset:offset + size]
    if len(body) != size:
        raise ValueError('truncated initramfs member')
    offset = (offset + size + 3) & ~3
    if name == 'TRAILER!!!':
        break
    if name in members:
        raise ValueError('duplicate initramfs member')
    members[name.removeprefix('./')] = hashlib.sha256(body).hexdigest()
for folder in ('apple', 'brcm'):
    for source in (firmware / folder).iterdir():
        name = 'usr/lib/firmware/' + source.relative_to(firmware).as_posix()
        if members.get(name) != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError('initramfs firmware mismatch: ' + name)
release = thermal.parents[3].name
name = 'usr/lib/modules/' + release + '/kernel/drivers/thermal/apple-pmp-thermal.ko'
if members.get(name) != hashlib.sha256(thermal.read_bytes()).hexdigest():
    raise ValueError('initramfs thermal module mismatch')
if not {'init', 'usr/lib/systemd/systemd', 'usr/lib/firmware/regulatory.db'} <= members.keys():
    raise ValueError('incomplete systemd initramfs')
print('initramfs: exact seven firmware files, matching thermal module and systemd init verified')

"""Read every early, compressed and trailing initramfs archive without execution."""
import ctypes
import hashlib
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys


def members(data):
    result = {}
    offset = 0
    while offset < len(data):
        if data[offset] == 0:
            offset += 1
            continue
        if data[offset:offset + 4] == b'\x28\xb5\x2f\xfd':
            library = ctypes.CDLL('libzstd.so.1')
            library.ZSTD_findFrameCompressedSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            library.ZSTD_findFrameCompressedSize.restype = ctypes.c_size_t
            library.ZSTD_isError.argtypes = [ctypes.c_size_t]
            library.ZSTD_isError.restype = ctypes.c_uint
            source = ctypes.create_string_buffer(data[offset:])
            length = library.ZSTD_findFrameCompressedSize(source, len(data) - offset)
            if library.ZSTD_isError(length) or not 0 < length <= len(data) - offset:
                raise ValueError('invalid zstd initramfs frame')
            expanded = subprocess.run(['zstd', '-d', '-c'], input=data[offset:offset + length],
                                      capture_output=True, check=True).stdout
            for name, value in members(expanded).items():
                add_member(result, name, value)
            offset += length
            continue
        start = offset
        header = data[offset:offset + 110]
        if len(header) != 110 or header[:6] != b'070701':
            raise ValueError('unsupported or malformed initramfs archive')
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        if not 1 <= namesize <= 4096:
            raise ValueError('invalid initramfs name size')
        raw = data[offset + 110:offset + 110 + namesize]
        if len(raw) != namesize or raw[-1:] != b'\0' or b'\0' in raw[:-1]:
            raise ValueError('invalid initramfs member name')
        name = raw[:-1].decode()
        offset = start + ((110 + namesize + 3) & ~3)
        body = data[offset:offset + size]
        if len(body) != size:
            raise ValueError('truncated initramfs member')
        offset += (size + 3) & ~3
        if name == 'TRAILER!!!':
            continue
        normalized = str(PurePosixPath(name))
        if PurePosixPath(normalized).is_absolute() or '..' in PurePosixPath(normalized).parts:
            raise ValueError('unsafe initramfs member name')
        add_member(result, normalized, (mode, hashlib.sha256(body).hexdigest()))
    return result


def add_member(result, name, value):
    if name in result and not ((stat.S_ISDIR(value[0]) or stat.S_ISLNK(value[0]))
                               and result[name] == value):
        raise ValueError('duplicate initramfs member: ' + name)
    result[name] = value


def verify(image, thermal):
    records = members(image.read_bytes())
    allowed = {'usr/lib/firmware/regulatory.db', 'usr/lib/firmware/regulatory.db.p7s'}
    for name, (mode, digest) in records.items():
        if not stat.S_ISDIR(mode) and name.startswith(('vendorfw/', 'usr/lib/firmware/', 'lib/firmware/')) and name not in allowed:
            raise ValueError('distributed initramfs contains vendor firmware: ' + name)
    release = thermal.parents[3].name
    tree = thermal.parents[3]
    for path, (mode, digest) in records.items():
        if path.startswith(('usr/lib/modules/', 'lib/modules/')):
            relative = path.split('lib/modules/', 1)[1]
            if relative.split('/')[0] != release:
                raise ValueError('initramfs contains a different kernel release: ' + path)
            if path.endswith(('.ko.zst', '.ko.xz', '.ko.gz')):
                raise ValueError('unexpected compressed initramfs module: ' + path)
            if path.endswith('.ko'):
                module = tree.parent / relative
                if not module.is_file() or hashlib.sha256(module.read_bytes()).hexdigest() != digest:
                    raise ValueError('initramfs module differs from kernel build: ' + path)
        if any(marker in path for marker in
               ('neo_poll_tty', 'neo-installer-debug', 'neo-wifi-debug', 'Image.wifi-debug', 'Image.beacon')):
            raise ValueError('diagnostic initramfs member: ' + path)
    name = 'usr/lib/modules/' + release + '/kernel/drivers/thermal/apple-pmp-thermal.ko'
    if records.get(name, (None, None))[1] != hashlib.sha256(thermal.read_bytes()).hexdigest():
        raise ValueError('initramfs thermal module mismatch')
    if not {'init', 'usr/lib/systemd/systemd', 'usr/lib/firmware/regulatory.db'} <= records.keys():
        raise ValueError('incomplete systemd initramfs')
    print('all initramfs archives: no vendor firmware, matching thermal module and systemd init verified')


if __name__ == '__main__':
    verify(*map(Path, sys.argv[1:]))

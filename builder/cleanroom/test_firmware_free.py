"""Synthetic multi-archive regressions for the firmware-free image verifier."""
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from verify_initramfs import members, verify


def cpio(name, body=b'fixture'):
    def record(name, body):
        fields = [1, stat.S_IFREG | 0o644, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(name) + 1, 0]
        header = b'070701' + ''.join('%08x' % value for value in fields).encode()
        result = header + name.encode() + b'\0'
        result += b'\0' * (-len(result) % 4)
        result += body + b'\0' * (-len(body) % 4)
        return result
    return record(name, body) + record('TRAILER!!!', b'')


class FirmwareFreeInitramfsTests(unittest.TestCase):
    def test_all_early_compressed_and_trailing_archives_are_read(self):
        compressed = subprocess.run(['zstd', '-q', '-c'], input=cpio('main'), capture_output=True, check=True).stdout
        data = cpio('./early') + b'\0' * 512 + compressed + cpio('trailing')
        self.assertEqual(set(members(data)), {'early', 'main', 'trailing'})

    def test_firmware_in_early_or_trailing_archive_is_rejected(self):
        compressed = subprocess.run(['zstd', '-q', '-c'], input=cpio('main'), capture_output=True, check=True).stdout
        firmware = cpio('./usr/lib/firmware/apple/tpmtfw-j713.bin')
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'initramfs'
            for data in (firmware + compressed, compressed + firmware):
                image.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'contains vendor firmware'):
                    verify(image, Path(directory) / 'not-needed')

    def test_every_initramfs_module_must_match_the_compiled_release_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thermal = root / 'lib/modules/test-release/kernel/drivers/thermal/apple-pmp-thermal.ko'
            thermal.parent.mkdir(parents=True)
            thermal.write_bytes(b'thermal')
            image = root / 'initramfs'
            base = cpio('init') + cpio('usr/lib/systemd/systemd') + cpio('usr/lib/firmware/regulatory.db')
            base += cpio('usr/lib/modules/test-release/kernel/drivers/thermal/apple-pmp-thermal.ko', b'thermal')
            for member in ('usr/lib/modules/test-release+/extra.ko',
                           'usr/lib/modules/test-release/extra.ko',
                           'usr/lib/modules/test-release/extra.ko.zst', 'neo-wifi-debug.cpio.gz'):
                image.write_bytes(base + cpio(member))
                with self.subTest(member=member), self.assertRaises(ValueError):
                    verify(image, thermal)
            image.write_bytes(base)
            verify(image, thermal)

    def test_normalized_duplicates_and_malformed_trailing_data_are_rejected(self):
        for data in (cpio('./same') + cpio('same'), cpio('../escape'), cpio('valid') + b'unknown', cpio('cut')[:-5]):
            with self.subTest(data=data[-20:]), self.assertRaises(ValueError):
                members(data)


if __name__ == '__main__':
    unittest.main()

"""Protect both disk handoffs and the Neo EFI load boundary."""
import gzip
import struct
import unittest

from build_boot import disk_payload, kernel_command_line


class SharedBootTests(unittest.TestCase):
    def test_disk_payload_keeps_both_trees_and_no_early_terminator(self):
        trees = []
        for model in (b'apple,j713', b'apple,j700'):
            tree = bytearray(64)
            struct.pack_into('>II', tree, 0, 0xd00dfeed, len(tree))
            tree[40:50] = model
            trees.append(bytes(tree))
        uboot = bytearray(64)
        uboot[56:60] = b'ARM\x64'
        struct.pack_into('<Q', uboot, 16, 4096)
        payload = disk_payload(b'stage2', trees, bytes(uboot))
        prefix = b'stage2' + b''.join(trees)
        self.assertTrue(payload.startswith(prefix))
        self.assertEqual(payload[len(prefix):], gzip.compress(bytes(uboot).ljust(4096, b'\x00'), mtime=0))

    def test_neo_idle_workarounds_do_not_change_m4_command_line(self):
        root = '4f4d5801-524f-4f54-8713-000000000001'
        m4 = kernel_command_line(root, 'j713')
        neo = kernel_command_line(root, 'j700')
        self.assertNotIn('idle=nop', m4)
        self.assertEqual(neo, m4 + ' idle=nop arm64.nowfxt')
        for line in (m4, neo):
            self.assertIn('root=UUID=' + root, line)
            self.assertIn('systemd.unit=graphical.target', line)

    def test_invalid_or_oversized_uboot_is_rejected(self):
        for size in (0, 63, 64 * 1024**2 + 1):
            image = bytearray(64)
            image[56:60] = b'ARM\x64'
            struct.pack_into('<Q', image, 16, size)
            with self.assertRaises(ValueError):
                disk_payload(b'stage2', [], bytes(image))


if __name__ == '__main__':
    unittest.main()

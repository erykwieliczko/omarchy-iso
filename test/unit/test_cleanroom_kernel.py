"""Regression coverage for requirements missing from the first J713 image."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_kernel", ROOT / "builder/cleanroom/verify_kernel.py")
kernel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kernel)


class KernelRequirementsTest(unittest.TestCase):
    def test_original_booted_config_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "CONFIG_CRYPTO_USER_API_HASH"):
            kernel.verify_config(kernel.RECIPE / "j713-base.config")

    def test_wifi_fix_alone_still_rejects_missing_firewall(self):
        self.check_fragment("CONFIG_NF_TABLES=m", "# CONFIG_NF_TABLES is not set", "CONFIG_NF_TABLES")

    def test_pacman_sandbox_requires_landlock(self):
        self.check_fragment("CONFIG_SECURITY_LANDLOCK=y",
                            "# CONFIG_SECURITY_LANDLOCK is not set", "CONFIG_SECURITY_LANDLOCK")

    def test_iwd_requires_private_key_parser(self):
        self.check_fragment("CONFIG_PKCS8_PRIVATE_KEY_PARSER=m",
                            "# CONFIG_PKCS8_PRIVATE_KEY_PARSER is not set", "CONFIG_PKCS8_PRIVATE_KEY_PARSER")

    def test_speaker_driver_cannot_be_enabled_by_base_config(self):
        self.check_fragment("# CONFIG_SND_SOC_APPLE_MACAUDIO is not set",
                            "CONFIG_SND_SOC_APPLE_MACAUDIO=m", "CONFIG_SND_SOC_APPLE_MACAUDIO")

    def test_builtin_satisfies_a_module_requirement(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config"
            config.write_text((kernel.RECIPE / "omarchy.config").read_text().replace(
                "CONFIG_NF_TABLES=m", "CONFIG_NF_TABLES=y"))
            kernel.verify_config(config)

    def test_missing_module_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary)
            (tree / "modules.order").write_text("kernel/net/netfilter/nf_tables.ko\n")
            with self.assertRaisesRegex(ValueError, "missing matching module"):
                kernel.module_paths(tree)

    def test_module_path_escape_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary)
            (tree / "modules.order").write_text("../nf_tables.ko\n")
            with self.assertRaisesRegex(ValueError, "unsafe module order"):
                kernel.module_paths(tree)

    def test_boot_arguments_keep_logs_out_of_setup_console(self):
        sys.path.insert(0, str(ROOT / "builder/cleanroom"))
        try:
            from build_boot import kernel_command_line
            root_uuid = "4f4d5801-524f-4f54-8713-000000000001"
            args = kernel_command_line(root_uuid).split()
            self.assertIn("loglevel=3", args)
            self.assertNotIn("earlycon", args)
            self.assertIn("root=UUID=" + root_uuid, args)
            self.assertIn("systemd.unit=graphical.target", args)
            with self.assertRaises(ValueError):
                kernel_command_line(root_uuid + " init=/bin/sh")
        finally:
            sys.path.pop(0)

    def test_package_makes_private_build_modules_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "payload"
            tree = payload / "lib/modules/7.1.9-omarchy-j713.3"
            tree.mkdir(parents=True)
            tree.chmod(0o750)
            module = tree / "test.ko"
            module.write_bytes(b"module fixture")
            module.chmod(0o640)
            for name in ("Image", "config", "build-receipt.json"):
                (payload / name).write_text("fixture\n")
            (payload / "kernel.release").write_text(tree.name + "\n")
            package = root / "package"
            subprocess.run(["/bin/bash", "-c", 'set -euo pipefail; source "$1"; package',
                            "test-package", str(kernel.RECIPE / "PKGBUILD")],
                           env=dict(os.environ, OMARCHY_CLEANROOM_KERNEL_SOURCE=str(payload),
                                    pkgdir=str(package)), check=True)
            installed = package / "usr/lib/modules" / tree.name
            self.assertEqual(installed.stat().st_mode & 0o777, 0o755)
            self.assertEqual((installed / "test.ko").stat().st_mode & 0o777, 0o644)
            self.assertEqual((installed / "pkgbase").stat().st_mode & 0o777, 0o644)
            self.assertEqual((installed / "test.ko").read_bytes(), module.read_bytes())

    def check_fragment(self, before, after, expected_error):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config"
            config.write_text((kernel.RECIPE / "omarchy.config").read_text().replace(before, after))
            with self.assertRaisesRegex(ValueError, expected_error):
                kernel.verify_config(config)


if __name__ == "__main__":
    unittest.main()

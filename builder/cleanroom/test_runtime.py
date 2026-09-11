"""Regression tests for the missing browser helper in the 2.0.1 image."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import runtime


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = self.root / "inputs"
        self.target = self.root / "target"
        for name in runtime.FILES:
            path = self.inputs / "runtime" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# setup file\n")
        (self.inputs / "runtime/install/helpers/browser-policy.sh").write_text(
            'source "${BASH_SOURCE[0]%/*}/as-root.sh"\n'
            'browser_policy_setup_dir() { as_root true; }\n'
        )
        (self.inputs / "runtime/install/helpers/as-root.sh").write_text(
            'as_root() { "$@"; }\n'
        )

    def test_complete_helper_chain_loads(self):
        runtime.install(self.inputs, self.target)
        runtime.verify(self.inputs, self.target)

    def test_201_missing_helpers_rejected(self):
        runtime.install(self.inputs, self.target)
        for name in ("browser-policy.sh", "as-root.sh"):
            (self.target / "usr/share/omarchy/install/helpers" / name).unlink()
        with self.assertRaisesRegex(ValueError, "browser-policy.sh"):
            runtime.verify(self.inputs, self.target)

    def test_nested_helper_cannot_be_omitted(self):
        runtime.install(self.inputs, self.target)
        (self.target / "usr/share/omarchy/install/helpers/as-root.sh").unlink()
        with self.assertRaisesRegex(ValueError, "as-root.sh"):
            runtime.verify(self.inputs, self.target)

    def test_new_unstaged_nested_dependency_fails_loading(self):
        with (self.inputs / "runtime/install/helpers/as-root.sh").open("a") as writer:
            writer.write('source "${BASH_SOURCE[0]%/*}/missing.sh"\n')
        with self.assertRaises(subprocess.CalledProcessError):
            runtime.install(self.inputs, self.target)

    def test_stale_standalone_provisioner_rejected(self):
        runtime.install(self.inputs, self.target)
        (self.target / "usr/bin/omarchy-provision-owner").write_text("old version")
        with self.assertRaisesRegex(ValueError, "usr/bin/omarchy-provision-owner"):
            runtime.verify(self.inputs, self.target)

    def test_stale_browser_setter_rejected(self):
        runtime.install(self.inputs, self.target)
        (self.target / "usr/bin/omarchy-theme-set-browser").write_text("old setter")
        with self.assertRaisesRegex(ValueError, "usr/bin/omarchy-theme-set-browser"):
            runtime.verify(self.inputs, self.target)

    def test_missing_browser_sudo_rule_rejected(self):
        runtime.install(self.inputs, self.target)
        (self.target / "etc/sudoers.d/omarchy-theme-browser").unlink()
        with self.assertRaisesRegex(ValueError, "sudoers.d/omarchy-theme-browser"):
            runtime.verify(self.inputs, self.target)

    def test_writable_sudo_rule_rejected(self):
        runtime.install(self.inputs, self.target)
        (self.target / "etc/sudoers.d/omarchy-theme-browser").chmod(0o666)
        with self.assertRaisesRegex(ValueError, "permissions changed"):
            runtime.verify(self.inputs, self.target)

    def test_packaged_absolute_symlink_replaced_without_touching_referent(self):
        outside = self.root / "outside-command"
        outside.write_text("untouched")
        link = self.target / "usr/share/omarchy/bin/omarchy-provision-owner"
        link.parent.mkdir(parents=True)
        link.symlink_to(outside)
        runtime.install(self.inputs, self.target)
        self.assertFalse(link.is_symlink())
        self.assertEqual(outside.read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()

"""Install and verify the first-run runtime overlay as one dependency set."""
from pathlib import Path
import shutil
import subprocess
import sys


FILES = {
    "bin/omarchy-provision-owner": (
        "usr/bin/omarchy-provision-owner",
        "usr/share/omarchy/bin/omarchy-provision-owner",
    ),
    **{name: ("usr/share/omarchy/" + name,) for name in (
        "install/provisioning/setup-form.sh",
        "install/provisioning/wifi-country.sh",
        "install/helpers/browser-policy.sh",
        "install/helpers/as-root.sh",
    )},
}
REQUIRED_ARTIFACTS = {"runtime/" + name for name in FILES}


def install(inputs, target):
    for name, destinations in FILES.items():
        source = inputs / "runtime" / name
        for destination in destinations:
            path = target / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            # Base packages can expose /usr/share commands as absolute symlinks.
            # Replace the link itself, never follow it into the build host.
            if path.is_symlink():
                path.unlink()
            shutil.copyfile(source, path)
            path.chmod(0o755 if name.startswith("bin/") else 0o644)
    verify(inputs, target)


def verify(inputs, target):
    for name, destinations in FILES.items():
        expected = (inputs / "runtime" / name).read_bytes()
        for destination in destinations:
            path = target / destination
            if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
                raise ValueError("first-run runtime file missing or changed: " + destination)
    # Load the actual helper chain without invoking its machine-policy writes.
    # This catches missing nested sources before an owner account is created.
    subprocess.run([
        "/bin/bash", "--noprofile", "--norc", "-eu", "-c",
        'source "$1"; declare -F browser_policy_setup_dir as_root >/dev/null',
        "runtime-check", str(target / "usr/share/omarchy/install/helpers/browser-policy.sh"),
    ], check=True, env={"PATH": "/usr/bin:/bin"})


if __name__ == "__main__":
    operation, inputs, target = sys.argv[1:]
    {"install": install, "verify": verify}[operation](Path(inputs), Path(target))

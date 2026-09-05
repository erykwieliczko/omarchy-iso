"""Cross-compile the pinned private J713 kernel and every configured module."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess

from verify_kernel import RECIPE, digest, verify_artifacts, verify_config


def capture(*command):
    return subprocess.check_output(command, text=True).strip()


def build(workspace, rust_toolchain):
    workspace = workspace.resolve()
    rust_toolchain = rust_toolchain.resolve()
    source = workspace / "source"
    output = workspace / "build"
    lock = json.loads((RECIPE / "build-lock.json").read_text())
    baseline = RECIPE / "j713-base.config"
    fragment = RECIPE / "omarchy.config"
    revision = capture("git", "-C", str(source), "rev-parse", "HEAD")
    if revision != lock["source_revision"]:
        raise ValueError("source checkout does not match the accepted revision")
    if capture("git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("kernel source checkout must be clean")
    if digest(baseline) != lock["base_config_sha256"]:
        raise ValueError("accepted hardware configuration changed")
    rustc = rust_toolchain / "bin/rustc"
    versions = {
        "clang": capture("clang", "--version").splitlines()[0],
        "lld": capture("ld.lld", "--version"),
        "rustc": capture(str(rustc), "--version"),
        "bindgen": capture("bindgen", "--version"),
    }
    if versions["clang"] != "clang version " + lock["clang_version"]:
        raise ValueError("unexpected Clang version")
    if not versions["lld"].startswith("LLD " + lock["clang_version"] + " "):
        raise ValueError("unexpected LLD version")
    if versions["rustc"] != lock["rustc_version"] or versions["bindgen"] != lock["bindgen_version"]:
        raise ValueError("unexpected Rust or bindgen version")
    destination = workspace / "artifacts" / lock["kernel_release"]
    if destination.exists():
        raise ValueError("artifact output already exists; preserve it and select a new build release")
    jobs = int(os.environ.get("OMARCHY_BUILD_JOBS", "10"))
    if jobs < 1:
        raise ValueError("OMARCHY_BUILD_JOBS must be positive")
    output.mkdir(exist_ok=True)
    make = ["make", "-C", str(source), f"O={output}", "ARCH=arm64", "LLVM=1",
            f"RUSTC={rustc}", "LOCALVERSION=", f"-j{jobs}"]
    env = dict(os.environ, KBUILD_BUILD_USER="omarchy", KBUILD_BUILD_HOST="builder",
               KBUILD_BUILD_VERSION="1", KBUILD_BUILD_TIMESTAMP=capture(
                   "git", "-C", str(source), "show", "-s", "--format=%cD", "HEAD"))
    with (workspace / "build.log").open("a") as log:
        def run(command):
            print("Running: " + " ".join(map(str, command)), flush=True)
            log.write("\n$ " + " ".join(map(str, command)) + "\n")
            log.flush()
            subprocess.run(list(map(str, command)), check=True, env=env,
                           stdout=log, stderr=subprocess.STDOUT)

        run(["/bin/bash", source / "scripts/kconfig/merge_config.sh", "-m", "-O", output,
             baseline, fragment])
        run(make + ["olddefconfig"])
        # kernelrelease skips configuration synchronization and can read the
        # previous build's LOCALVERSION from include/config/auto.conf.
        run(make + ["syncconfig"])
        verify_config(output / ".config")
        release = subprocess.check_output(make + ["-s", "--no-print-directory", "kernelrelease"],
                                          env=env, text=True).strip()
        if release != lock["kernel_release"]:
            raise ValueError("unexpected resolved kernel release: " + release)
        run(make + ["Image", "dtbs", "modules"])
        verify_config(output / ".config")
        destination.mkdir(parents=True, exist_ok=False)
        run(make + ["modules_install", f"INSTALL_MOD_PATH={destination}", "DEPMOD=true"])
        tree = destination / "lib/modules" / release
        for name in ("build", "source"):
            path = tree / name
            if path.is_symlink():
                path.unlink()
        expected_modules = {"kernel/" + str(Path(n).with_suffix(".ko"))
                            for n in (output / "modules.order").read_text().splitlines()}
        if expected_modules != set((tree / "modules.order").read_text().splitlines()):
            raise ValueError("modules_install did not stage the complete build")
        run(["depmod", "-b", destination, release])
        for origin, name in ((output / "arch/arm64/boot/Image", "Image"),
                             (output / "arch/arm64/boot/dts/apple/t8132-j713.dtb", "t8132-j713.dtb"),
                             (output / ".config", "config"), (output / "System.map", "System.map")):
            shutil.copyfile(origin, destination / name)
        (destination / "kernel.release").write_text(release + "\n")
        for path in [destination, *destination.rglob("*")]:
            if path.is_symlink():
                raise ValueError("unexpected installed module symlink")
            path.chmod(0o755 if path.is_dir() else 0o644)
        verification = verify_artifacts(destination, check_receipt=False)
        receipt = {
            "schema_version": 1, "source_revision": revision, "kernel_release": release,
            "base_config_sha256": digest(baseline), "fragment_sha256": digest(fragment),
            "builder_sha256": digest(Path(__file__)), "verifier_sha256": digest(RECIPE.parent / "verify_kernel.py"),
            "toolchain": versions, "verification": verification,
            "artifacts": {p.relative_to(destination).as_posix(): {
                "size_bytes": p.stat().st_size, "sha256": digest(p)}
                for p in sorted(destination.rglob("*")) if p.is_file()},
        }
        receipt_path = destination / "build-receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        receipt_path.chmod(0o644)
        print(json.dumps(verify_artifacts(destination), indent=2), flush=True)
        print("Kernel artifacts: " + str(destination), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path, help="workspace with a clean pinned source/ checkout")
    parser.add_argument("--rust-toolchain", type=Path, required=True)
    args = parser.parse_args()
    with (args.workspace / ".build.lock").open("w") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build(**vars(args))

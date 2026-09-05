"""Validate resolved distribution requirements and the complete module payload."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

RECIPE = Path(__file__).resolve().parent / "kernel"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def config_values(path):
    values = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"(CONFIG_\w+)=(.*)", line)
        disabled = re.fullmatch(r"# (CONFIG_\w+) is not set", line)
        if match:
            values[match[1]] = match[2]
        elif disabled:
            values[disabled[1]] = "n"
    return values


def verify_config(config, fragment=RECIPE / "omarchy.config"):
    actual = config_values(config)
    errors = []
    for key, wanted in config_values(fragment).items():
        found = actual.get(key, "n")
        if found != wanted and not (wanted == "m" and found == "y"):
            errors.append(f"{key}: requires {wanted}, resolved to {found}")
    if errors:
        raise ValueError("kernel requirements failed:\n" + "\n".join(errors))
    return actual


def module_paths(tree):
    paths = []
    for name in (tree / "modules.order").read_text().splitlines():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".ko":
            raise ValueError("unsafe module order entry: " + name)
        path = tree / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError("missing matching module: " + str(path))
        paths.append(path)
    if not paths:
        raise ValueError("empty module payload")
    return paths


def verify_artifacts(directory, check_receipt=True):
    verify_config(directory / "config")
    release = (directory / "kernel.release").read_text().strip()
    lock = json.loads((RECIPE / "build-lock.json").read_text())
    if release != lock["kernel_release"]:
        raise ValueError("unexpected kernel release")
    tree = directory / "lib/modules" / release
    for path in [directory, *directory.rglob("*")]:
        if path.is_symlink():
            raise ValueError("kernel payload contains a symlink: " + str(path))
        if path.stat().st_mode & 0o777 != (0o755 if path.is_dir() else 0o644):
            raise ValueError("kernel payload permissions are not normalized: " + str(path))
    for name in ("modules.dep", "modules.dep.bin", "modules.alias", "modules.alias.bin",
                 "modules.builtin", "modules.builtin.modinfo"):
        if not (tree / name).is_file():
            raise ValueError("missing module index: " + name)
    paths = module_paths(tree)
    for offset in range(0, len(paths), 128):
        batch = paths[offset:offset + 128]
        result = subprocess.run(["modinfo", "-F", "vermagic", *map(str, batch)],
                                check=True, capture_output=True, text=True)
        versions = result.stdout.splitlines()
        if len(versions) != len(batch) or any(v.split()[0] != release for v in versions):
            raise ValueError("module version does not match Image")
    image = (directory / "Image").read_bytes()
    if image[56:60] != b"ARM\x64":
        raise ValueError("Image is not an ARM64 kernel")
    if (directory / "t8132-j713.dtb").read_bytes()[:4] != b"\xd0\x0d\xfe\xed":
        raise ValueError("invalid J713 device tree")
    if check_receipt:
        receipt = json.loads((directory / "build-receipt.json").read_text())
        if receipt["source_revision"] != lock["source_revision"] or receipt["kernel_release"] != release:
            raise ValueError("kernel build identity mismatch")
        actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
                  if p.is_file() and p.name != "build-receipt.json"}
        if actual != set(receipt["artifacts"]):
            raise ValueError("kernel receipt file set mismatch")
        for name, record in receipt["artifacts"].items():
            path = directory / name
            if path.stat().st_size != record["size_bytes"] or digest(path) != record["sha256"]:
                raise ValueError("kernel artifact changed: " + name)
    return {"kernel_release": release, "modules_verified": len(paths)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args()
    if args.config_only:
        verify_config(args.path)
        print("kernel configuration requirements passed")
    else:
        print(json.dumps(verify_artifacts(args.path), indent=2))

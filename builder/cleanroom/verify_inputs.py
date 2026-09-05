"""Check every admitted cleanroom payload input before image mutation."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

from verify_kernel import verify_artifacts


def verify(directory):
    manifest = json.loads((directory / "j713-boot-inputs.json").read_text())
    if manifest["schema_version"] != 1 or manifest["profile"]["device_identifier"] != "apple,j713":
        raise ValueError("unsupported cleanroom payload input")
    required = {"kernel/Image", "kernel/config", "kernel/t8132-j713.dtb", "m1n1-stage2.bin", "u-boot.bin",
                "kernel/kernel.release", "kernel/build-receipt.json",
                "linux-omarchy-j713-7.1.9.j713-4-aarch64.pkg.tar.zst",
                "aquamarine-0.14.0-3-aarch64.pkg.tar.zst"}
    if not required.issubset(manifest["artifacts"]):
        raise ValueError("incomplete cleanroom artifact set")
    for name, expected in manifest["artifacts"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
            raise ValueError("unsafe cleanroom artifact name")
        path = directory / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size != expected["size_bytes"]:
            raise ValueError("cleanroom artifact file type or size changed: " + name)
        digest = hashlib.sha256()
        with path.open("rb") as reader:
            while chunk := reader.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected["sha256"]:
            raise ValueError("cleanroom artifact digest changed: " + name)
    verify_artifacts(directory / "kernel")
    return manifest


if __name__ == "__main__":
    verify(Path(sys.argv[1]))

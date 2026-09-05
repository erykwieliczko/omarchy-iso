"""Verify and sparsely extract the pinned Omarchy base for a cleanroom variant."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

BASE_SHA256 = "ccd48c3ce69962cae6a574f630feca32072f18f610a2b5b84b07993fd2cc18e9"
BASE_SIZE = 3638034944
MEMBERS = {"root.img": 34359738368, "boot.img": 2147483648, "omarchy-volume.icns": 42899}


def extract_base(source, destination):
    if source.is_symlink() or not source.is_file() or source.stat().st_size != BASE_SIZE:
        raise ValueError("base package size or file type differs from admitted release")
    digest = hashlib.sha256()
    with source.open("rb") as reader:
        while chunk := reader.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != BASE_SHA256:
        raise ValueError("base package digest differs from admitted release")
    if destination.exists() or destination.is_symlink():
        raise ValueError("base extraction destination already exists")
    with tempfile.TemporaryDirectory(prefix=".base-images-", dir=destination.parent) as temporary:
        tree = Path(temporary) / "images"
        tree.mkdir()
        with zipfile.ZipFile(source) as archive:
            for name, size in MEMBERS.items():
                matches = [item for item in archive.infolist() if item.filename == name]
                if len(matches) != 1 or matches[0].file_size != size:
                    raise ValueError("base image member size or identity changed")
                image_hash = hashlib.sha256()
                with archive.open(matches[0]) as reader, (tree / name).open("xb") as writer:
                    count = 0
                    while chunk := reader.read(1024 * 1024):
                        image_hash.update(chunk)
                        count += len(chunk)
                        if chunk == bytes(len(chunk)):
                            writer.seek(len(chunk), 1)
                        else:
                            writer.write(chunk)
                    writer.truncate(size)
                if count != size:
                    raise ValueError("base image member is truncated")
                (tree / (name + ".sha256")).write_text(image_hash.hexdigest() + "\n")
        (tree / "base-input.json").write_text(json.dumps({
            "release": "v4.0.1-mac.2.9.090126", "sha256": BASE_SHA256,
            "size_bytes": BASE_SIZE, "public_release_authorized": False,
        }, indent=2) + "\n")
        tree.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    extract_base(args.source.resolve(), args.destination.absolute())

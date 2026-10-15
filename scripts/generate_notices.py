#!/usr/bin/env python3
"""Preserve full installed dependency licenses, including wheel-vendored libraries."""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    index = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        folder = args.destination / f"{name}-{dist.version}"
        folder.mkdir(exist_ok=True)
        licenses = []
        for file in dist.files or []:
            # Include LICENSE_GEOS, COPYING_QHULL, bundled BLAS licenses, etc.
            if not any(word in file.name.lower() for word in ("license", "copying", "notice")):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file() or source.suffix in (".py", ".pyc"):
                continue
            relative = Path(*[p for p in file.parts if p not in ("..", ".")])
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            licenses.append(str(relative))
        (folder / "METADATA.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
        index.append({"name": name, "version": dist.version, "license_files": licenses})
    python_license = Path(__file__).resolve().parent.parent / "packaging/PYTHON-LICENSE.txt"
    shutil.copyfile(python_license, args.destination / "PYTHON-LICENSE.txt")
    (args.destination / "INDEX.json").write_text(json.dumps({
        "python": sys.version, "python_license_sha256": hashlib.sha256(python_license.read_bytes()).hexdigest(),
        "scope": "Build environment inventory; includes tools as well as shipped dependencies. "
                 "Full wheel license texts include vendored native-library notices.",
        "distributions": index,
    }, indent=2) + "\n", encoding="utf-8")
    for required in ("numpy", "scipy", "shapely", "trimesh", "pyinstaller"):
        if not any(d["name"].lower() == required and d["license_files"] for d in index):
            raise SystemExit(f"Missing required full license material: {required}")


if __name__ == "__main__":
    main()

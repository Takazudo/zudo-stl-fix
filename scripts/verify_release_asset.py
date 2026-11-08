#!/usr/bin/env python3
"""Verify a locally built macOS release archive before or after it is attached to a GitHub Release.

The archive is built on a local Apple silicon Mac by scripts/release-macos-local.sh
(no macOS CI by owner decision). This check runs anywhere, including Linux CI.
"""
from __future__ import annotations

import argparse
import hashlib
import plistlib
import re
import sys
import zipfile
from pathlib import Path

APP = "zudo-stl-fix.app"
MAIN = f"{APP}/Contents/MacOS/ZudoSTLFix"
WORKER = f"{APP}/Contents/Helpers/STLWorker.app/Contents/MacOS/stl-worker"
BUILD_INFO = f"{APP}/Contents/Resources/BUILD-INFO.txt"
INFO_PLIST = f"{APP}/Contents/Info.plist"
MINIMUM_MACOS = "27.0"
MACHO_ARM64 = bytes.fromhex("cffaedfe0c000001")  # 64-bit little-endian Mach-O, CPU_TYPE_ARM64


class ReleaseError(Exception):
    pass


def archive_name(version: str) -> str:
    return f"zudo-stl-fix-{version}-macos-arm64.zip"


def check_checksum(archive: Path, checksum: Path) -> str:
    line = checksum.read_text(encoding="ascii").strip()
    match = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
    if not match:
        raise ReleaseError(f"{checksum.name}: expected one '<sha256>  <archive>' line")
    if match.group(2) != archive.name:
        raise ReleaseError(f"{checksum.name} names {match.group(2)}, not {archive.name}")
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != match.group(1):
        raise ReleaseError(f"{archive.name}: SHA-256 {actual} does not match {checksum.name}")
    return actual


def build_info_fields(text: str) -> dict:
    lines = text.splitlines()
    commits = [i for i, line in enumerate(lines) if re.fullmatch(r"[0-9a-f]{40}", line)]
    arch = [i for i, line in enumerate(lines) if line.startswith("architecture=")]
    if len(commits) != 1 or len(arch) != 1 or arch[0] < commits[0]:
        raise ReleaseError("BUILD-INFO.txt lacks one source commit followed by an architecture line")
    status = [line for line in lines[commits[0] + 1:arch[0]] if line.strip()]
    target = next((line for line in lines if line.startswith("deployment_target=")), "")
    return {"commit": lines[commits[0]], "dirty": status, "architecture": lines[arch[0]].split("=", 1)[1],
            "deployment_target": target.split("=", 1)[1].split()[0] if target else ""}


def check_archive(archive: Path, version: str, commit: str | None) -> dict:
    try:
        bundle = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise ReleaseError(f"{archive.name}: not a zip archive") from exc
    with bundle:
        names = set(bundle.namelist())
        for required in (MAIN, WORKER, BUILD_INFO, INFO_PLIST):
            if required not in names:
                raise ReleaseError(f"{archive.name}: missing {required}")
        for binary in (MAIN, WORKER):
            if bundle.read(binary)[:8] != MACHO_ARM64:
                raise ReleaseError(f"{binary} is not a thin arm64 Mach-O executable")
        info = plistlib.loads(bundle.read(INFO_PLIST))
        fields = build_info_fields(bundle.read(BUILD_INFO).decode("utf-8", "replace"))
    if info.get("CFBundleShortVersionString") != version:
        raise ReleaseError(f"Info.plist version {info.get('CFBundleShortVersionString')!r} is not {version!r}")
    if info.get("LSMinimumSystemVersion") != MINIMUM_MACOS:
        raise ReleaseError(f"LSMinimumSystemVersion {info.get('LSMinimumSystemVersion')!r} is not {MINIMUM_MACOS}")
    if fields["architecture"] != "arm64" or fields["deployment_target"] != MINIMUM_MACOS:
        raise ReleaseError(f"BUILD-INFO records {fields['architecture']} / {fields['deployment_target']}, "
                           f"not arm64 / {MINIMUM_MACOS}")
    if fields["dirty"]:
        raise ReleaseError("BUILD-INFO records uncommitted changes: " + "; ".join(fields["dirty"]))
    if commit and fields["commit"] != commit:
        raise ReleaseError(f"Built from {fields['commit']}, but the release tag points to {commit}")
    return fields


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="folder holding the archive and its .sha256")
    parser.add_argument("--version", required=True, help="app version, e.g. 0.1.0 (no leading v)")
    parser.add_argument("--commit", help="40-hex commit the release tag points to")
    args = parser.parse_args(argv)
    archive = args.directory / archive_name(args.version)
    checksum = archive.with_name(archive.name + ".sha256")
    try:
        for path in (archive, checksum):
            if not path.is_file():
                raise ReleaseError(f"missing {path.name}; build it with scripts/release-macos-local.sh on an Apple silicon Mac")
        digest = check_checksum(archive, checksum)
        fields = check_archive(archive, args.version, args.commit)
    except ReleaseError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print(f"PASS {archive.name}: sha256 {digest}, commit {fields['commit']}, arm64, macOS {MINIMUM_MACOS}+")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

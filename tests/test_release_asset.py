import hashlib
import plistlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_release_asset as v  # noqa: E402

COMMIT = "a" * 40
ARM64 = v.MACHO_ARM64 + b"\0" * 24
X86_64 = bytes.fromhex("cffaedfe07000001") + b"\0" * 24


def build_info(commit=COMMIT, dirty="", arch="arm64", target="27.0"):
    return (f"ProductVersion: 27.0.1\nPython 3.12.14\nnumpy==2.5.4\n{commit}\n{dirty}"
            f"architecture={arch}\ndeployment_target={target} (not proof of runtime compatibility)\n")


class ReleaseAssetTests(unittest.TestCase):
    def make(self, version="0.1.0", minimum="27.0", main=ARM64, info=None, omit=None, name=None):
        folder = self.temporary()
        archive = folder / (name or v.archive_name(version))
        members = {
            v.MAIN: main, v.WORKER: ARM64,
            v.BUILD_INFO: (info or build_info()).encode(),
            v.INFO_PLIST: plistlib.dumps({"CFBundleShortVersionString": version, "LSMinimumSystemVersion": minimum}),
        }
        with zipfile.ZipFile(archive, "w") as bundle:
            for member, data in members.items():
                if member != omit:
                    bundle.writestr(member, data)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (folder / (archive.name + ".sha256")).write_text(f"{digest}  {archive.name}\n")
        return folder

    def temporary(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def run_check(self, folder, version="0.1.0", commit=COMMIT):
        return v.main([str(folder), "--version", version, "--commit", commit])

    def test_valid_archive_passes(self):
        self.assertEqual(self.run_check(self.make()), 0)

    def test_missing_assets_fail(self):
        self.assertEqual(self.run_check(self.temporary()), 1)

    def test_tampered_archive_fails_checksum(self):
        folder = self.make()
        with open(folder / v.archive_name("0.1.0"), "ab") as stream:
            stream.write(b"x")
        self.assertEqual(self.run_check(folder), 1)

    def test_wrong_commit_dirty_tree_and_platform_fail(self):
        self.assertEqual(self.run_check(self.make(), commit="b" * 40), 1)
        self.assertEqual(self.run_check(self.make(info=build_info(dirty=" M README.md\n"))), 1)
        self.assertEqual(self.run_check(self.make(info=build_info(arch="x86_64"))), 1)
        self.assertEqual(self.run_check(self.make(info=build_info(target="14.0"))), 1)
        self.assertEqual(self.run_check(self.make(minimum="14.0")), 1)
        self.assertEqual(self.run_check(self.make(main=X86_64)), 1)

    def test_version_mismatch_and_missing_helper_fail(self):
        self.assertEqual(self.run_check(self.make(version="0.2.0"), version="0.1.0"), 1)
        self.assertEqual(self.run_check(self.make(omit=v.WORKER)), 1)

    def test_checksum_must_name_the_archive(self):
        folder = self.make()
        checksum = folder / (v.archive_name("0.1.0") + ".sha256")
        digest = checksum.read_text().split()[0]
        checksum.write_text(f"{digest}  other.zip\n")
        self.assertEqual(self.run_check(folder), 1)


if __name__ == "__main__":
    unittest.main()

"""Full-CLI regressions: outputs and reports never alias or overwrite inputs or each other."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "engine/stl_doctor.py"
RAIL = ROOT / "fixtures/originals/nuts-v2-40hp-double.stl"
BAR = ROOT / "fixtures/originals/bar-30hp.stl"
sys.path.insert(0, str(ROOT / "engine"))
import stl_doctor  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CLIFileSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.rail = self.root / "rail.stl"
        self.bar = self.root / "bar.stl"
        shutil.copyfile(RAIL, self.rail)
        shutil.copyfile(BAR, self.bar)
        self.out = self.root / "out"
        self.out.mkdir()
        self.report = self.root / "report.json"
        self.hashes = {self.rail: sha(RAIL), self.bar: sha(BAR)}

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True, timeout=600)

    def assertInputsUnchanged(self):
        for path, digest in self.hashes.items():
            self.assertTrue(path.is_file() and not path.is_symlink(), path)
            self.assertEqual(sha(path), digest, path)

    def assertRefused(self, result, text):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(text, result.stderr)
        self.assertInputsUnchanged()

    def assertValidRepair(self, path):
        stl = stl_doctor.load_stl(path)
        after = stl_doctor.audit(stl)
        self.assertFalse(after["failures"])
        self.assertEqual(after["surface_intersections"]["defect_pair_count"], 0)

    def test_output_symlink_to_another_batch_input_is_refused(self):
        (self.out / "rail-fixed.stl").symlink_to(self.bar)
        result = self.cli("repair", self.rail, self.bar, "--out-dir", self.out, "--report", self.report, "--overwrite")
        self.assertRefused(result, "is a symbolic link")
        self.assertFalse(self.report.exists())

    def test_output_hard_links_to_own_or_other_input_are_refused(self):
        for source in (self.rail, self.bar):
            with self.subTest(source=source.name):
                link = self.out / "rail-fixed.stl"
                os.link(source, link)
                result = self.cli("repair", self.rail, self.bar, "--out-dir", self.out, "--report", self.report, "--overwrite")
                self.assertRefused(result, f"hard link) for input {source}")
                self.assertFalse(self.report.exists())
                link.unlink()

    def test_report_hard_link_to_input_is_refused_in_check_and_repair(self):
        os.link(self.bar, self.report)
        for mode in ("check", "repair"):
            with self.subTest(mode=mode):
                result = self.cli(mode, self.rail, self.bar, "--out-dir", self.out, "--report", self.report, "--overwrite")
                self.assertRefused(result, f"hard link) for input {self.bar}")
                self.assertEqual(list(self.out.iterdir()), [])

    def test_report_symlink_is_refused(self):
        self.report.symlink_to(self.bar)
        result = self.cli("check", self.rail, "--report", self.report, "--overwrite")
        self.assertRefused(result, "symbolic link")
        other = self.root / "other.json"
        other.write_text("keep")
        self.report.unlink()
        self.report.symlink_to(other)
        result = self.cli("check", self.rail, "--report", self.report, "--overwrite")
        self.assertRefused(result, "symbolic link")
        self.assertEqual(other.read_text(), "keep")

    def test_report_hard_link_to_existing_output_is_refused(self):
        output = self.out / "rail-fixed.stl"
        output.write_bytes(b"previous output")
        os.link(output, self.report)
        result = self.cli("repair", self.rail, "--out-dir", self.out, "--report", self.report, "--overwrite")
        self.assertRefused(result, f"hard link) for output {output}")
        self.assertEqual(output.read_bytes(), b"previous output")

    def test_overwrite_replaces_unrelated_regular_files(self):
        output = self.out / "rail-fixed.stl"
        output.write_bytes(b"old")
        self.report.write_text("old")
        result = self.cli("repair", self.rail, self.bar, "--out-dir", self.out, "--report", self.report, "--overwrite")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertInputsUnchanged()
        self.assertValidRepair(output)
        report = json.loads(self.report.read_text())
        self.assertEqual([f["action"] for f in report["files"]], ["repaired", "unchanged"])
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["rail-fixed.stl"])
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith(".")), [])

    def test_existing_files_are_kept_without_overwrite(self):
        output = self.out / "rail-fixed.stl"
        os.link(self.bar, output)
        result = self.cli("repair", self.rail, "--out-dir", self.out, "--report", self.report)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Output exists", result.stderr)
        self.assertInputsUnchanged()
        self.assertEqual(json.loads(self.report.read_text())["files"][0]["action"], "error")
        result = self.cli("check", self.bar, "--report", self.report)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Report exists", result.stderr)
        self.assertEqual(json.loads(self.report.read_text())["mode"], "repair")
        self.assertInputsUnchanged()

    def test_output_substituted_with_input_link_during_repair_is_not_written_through(self):
        output = self.out / "rail-fixed.stl"
        real_repair = stl_doctor.repair

        def racing_repair(*args, **kwargs):
            result = real_repair(*args, **kwargs)
            os.link(self.bar, output)
            return result

        with mock.patch.object(stl_doctor, "repair", racing_repair), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            code = stl_doctor.main(["repair", str(self.rail), str(self.bar), "--out-dir", str(self.out),
                                    "--report", str(self.report), "--overwrite"])
        self.assertEqual(code, 2)
        self.assertInputsUnchanged()
        report = json.loads(self.report.read_text())
        self.assertEqual(report["files"][0]["action"], "error")
        self.assertIn("hard link", report["files"][0]["error"])
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["rail-fixed.stl"])

    def test_report_substituted_with_output_link_keeps_verified_output(self):
        output = self.out / "rail-fixed.stl"
        real_write = stl_doctor.write_safe

        def racing_write(path, *args, **kwargs):
            if path == self.report.parent.resolve() / self.report.name:
                os.link(output, path)
            return real_write(path, *args, **kwargs)

        with mock.patch.object(stl_doctor, "write_safe", racing_write), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            code = stl_doctor.main(["repair", str(self.rail), "--out-dir", str(self.out),
                                    "--report", str(self.report), "--overwrite"])
        self.assertEqual(code, 2)
        self.assertInputsUnchanged()
        self.assertValidRepair(output)


if __name__ == "__main__":
    unittest.main()

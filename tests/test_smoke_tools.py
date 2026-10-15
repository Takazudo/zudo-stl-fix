"""Test packaging smoke orchestration, not a macOS bundle or native application."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

spec = importlib.util.spec_from_file_location("smoke_bundle", Path(__file__).resolve().parents[1] / "scripts/smoke_bundle.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeProcessTests(unittest.TestCase):
    def run_script(self, script, **kwargs):
        return smoke.run_bounded([sys.executable, "-c", script], timeout=3, **kwargs)

    def test_drains_both_streams_and_closes_input(self):
        result = self.run_script("import sys; d=sys.stdin.buffer.read(); sys.stderr.write('diagnostic'*1000); sys.stdout.buffer.write(d)", input_bytes=b"request\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "request\n")
        self.assertEqual(len(result.stderr), 10000)

    def test_stdout_flood_fails_while_process_is_alive(self):
        with self.assertRaisesRegex(RuntimeError, "stdout bound"):
            self.run_script("import os;\nwhile True: os.write(1,b'x'*4096)", stdout_limit=8192)

    def test_stderr_flood_fails_while_process_is_alive(self):
        with self.assertRaisesRegex(RuntimeError, "stderr bound"):
            self.run_script("import os;\nwhile True: os.write(2,b'x'*4096)", stderr_limit=8192)

    def test_timeout_kills_worker(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            smoke.run_bounded([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1)

    def test_success_looking_text_with_abnormal_exit_raises(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_script("print('success'); raise SystemExit(7)", check=True)

    def test_invalid_utf8_is_rejected(self):
        with self.assertRaises(UnicodeDecodeError):
            self.run_script("import os; os.write(1,b'\\xff')")

    def test_oversized_request_is_rejected_before_launch(self):
        with self.assertRaises(ValueError):
            smoke.run_bounded(["/does/not/exist"], input_bytes=b"x" * (16 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()

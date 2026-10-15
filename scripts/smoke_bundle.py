#!/usr/bin/env python3
"""Exercise relocated embedded helper with no developer Python/Homebrew on PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
import uuid


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_bounded(command, *, input_bytes=b"", cwd=None, env=None, timeout=180,
                stdout_limit=4 * 1024 * 1024, stderr_limit=1024 * 1024, check=False):
    """Drain both pipes while enforcing limits, including before process exit."""
    if len(input_bytes) > 16 * 1024:
        raise ValueError("Smoke request exceeds protocol bound")
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, cwd=cwd, env=env, start_new_session=True)
    deadline = time.monotonic() + timeout
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    pending = memoryview(input_bytes)
    try:
        with selectors.DefaultSelector() as selector:
            for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, timeout)
                for key, _ in selector.select(timeout=min(0.1, max(0, deadline - time.monotonic()))):
                    stream, name = key.fileobj, key.data
                    if name == "stdin":
                        try:
                            pending = pending[os.write(stream.fileno(), pending):]
                        except BrokenPipeError:
                            pending = memoryview(b"")
                        if not pending:
                            selector.unregister(stream)
                            stream.close()
                        continue
                    chunk = os.read(stream.fileno(), 64 * 1024)
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                        continue
                    buffers[name].extend(chunk)
                    limit = stdout_limit if name == "stdout" else stderr_limit
                    if len(buffers[name]) > limit:
                        raise RuntimeError(f"Embedded worker exceeded {name} bound")
        code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        result = subprocess.CompletedProcess(command, code, buffers["stdout"].decode("utf-8"),
                                             buffers["stderr"].decode("utf-8", errors="replace"))
        if check:
            result.check_returncode()
        return result
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def invoke(helper, root, source, env):
    job = root / str(uuid.uuid4())
    job.mkdir(mode=0o700)
    snapshot = job / "input.stl"
    shutil.copyfile(source, snapshot)
    before = sha(snapshot)
    job_id = str(uuid.uuid4())
    request = {"protocol_version": 1, "job_id": job_id,
               "operation": "check_and_repair", "input_path": str(snapshot),
               "staging_directory": str(job), "options": {
                   "weld_tolerance": 0.0, "max_faces": 20000, "max_pairs": 2000000}}
    process = run_bounded([str(helper)], input_bytes=(json.dumps(request) + "\n").encode(),
                          timeout=180, cwd=root, env=env)
    if process.returncode != 0:
        raise RuntimeError(f"Embedded worker exited {process.returncode}: {process.stderr[:4096]}")
    if len(process.stdout.encode()) > 4 * 1024 * 1024 or not process.stdout.endswith("\n"):
        raise RuntimeError("Worker stdout exceeded its bound or was truncated")
    events = [json.loads(line) for line in process.stdout.splitlines()]
    assert events and all(e["protocol_version"] == 1 and e["job_id"] == job_id for e in events)
    results = [e for e in events if e["event"] == "result"]
    assert len(results) == 1 and events[-1] == results[0], "Missing/duplicate/nonfinal result"
    assert sha(snapshot) == before, "Input snapshot changed"
    return job, results[0]


def inspect_native_dependencies(app):
    # Reject references that could make a passing checkout build depend on local tools.
    for path in app.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic not in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
            continue
        architecture = subprocess.check_output(["/usr/bin/lipo", "-archs", str(path)], text=True).split()
        assert platform.machine() in architecture, f"Missing native architecture: {path}"
        lines = subprocess.check_output(["/usr/bin/otool", "-L", str(path)], text=True).splitlines()[1:]
        for line in lines:
            dependency = line.strip().split(" (", 1)[0]
            assert not dependency.startswith("/") or dependency.startswith(("/System/Library/", "/usr/lib/")), \
                f"External native dependency: {path}: {dependency}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    if platform.system() != "Darwin":
        raise SystemExit("Run this check on macOS with an actual macOS app bundle.")
    repo = Path(__file__).resolve().parent.parent
    manifest = json.loads((repo / "fixtures/manifest.json").read_text())
    originals = [f for f in manifest["files"] if f["kind"] == "original"]
    assert len(originals) == 11
    with tempfile.TemporaryDirectory(prefix="zudo smoke 日本語 ") as temp:
        root = Path(temp).resolve()
        app = root / "moved app 日本語.app"
        subprocess.run(["/usr/bin/ditto", str(args.app.resolve()), str(app)], check=True)
        inspect_native_dependencies(app)
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        helper = app / "Contents/Helpers/STLWorker.app/Contents/MacOS/stl-worker"
        env = {"PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root),
               "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
        test = run_bounded([str(helper), "--self-test"], cwd=root, env=env, timeout=120, check=True)
        result = json.loads(test.stdout)
        assert result["protocol_version"] == 1 and result["self_test"] == "passed", result
        print(json.dumps({"embedded_self_test": result, "architecture": platform.machine()}, sort_keys=True))
        repaired = 0
        for fixture in originals:
            source = repo / fixture["path"]
            assert sha(source) == fixture["sha256"]
            job, result = invoke(helper, root, source, env)
            expected = "repaired" if fixture["expected_invalid_triangle_pairs"] else "unchanged"
            assert result["outcome"] == expected, (source.name, result)
            assert result["validation_status"] in ("PASS", "PASS_WITH_WARNINGS")
            audit = result["summary"]["after"] or result["summary"]["before"]
            assert audit["surface_intersections"]["complete"]
            assert audit["surface_intersections"]["defect_pair_count"] == 0
            assert audit["bounds"] == fixture["expected"]["bounds"]
            if expected == "repaired":
                repaired += 1
                assert any(w["code"] == "tiny_triangles" for w in result["warnings"]), \
                    "Default rail repairs must retain tiny-triangle warnings"
                candidate = result["candidate"]
                output = job / candidate["relative_path"]
                assert output.is_file() and not output.is_symlink() and output.parent.resolve() == job
                assert output.stat().st_size == candidate["byte_size"]
                assert sha(output) == candidate["sha256"]
                # A new process performs a full independent reload/audit of staged bytes.
                _, rechecked = invoke(helper, root, output, env)
                assert rechecked["outcome"] == "unchanged", rechecked
                assert rechecked["validation_status"] in ("PASS", "PASS_WITH_WARNINGS")
            else:
                assert result.get("candidate") is None
            assert sha(source) == fixture["sha256"]
            print(f"PASS {source.name}: {result['outcome']}")
        assert repaired == 2
    print("PASS relocated embedded helper: 11 originals and 2 serialized candidate rechecks; Finder/UI not exercised")


if __name__ == "__main__":
    main()

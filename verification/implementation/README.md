# Implementation verification — 2026-10-16 (Asia/Tokyo)

## Provenance and baseline

The owner created initial README commit
`a24ea321ff56beb328cea3e5b97e2b0c75d0b1fa` and complete handoff commit
`8737f55dff11d72e57888c5a046245a25bad38f4` on main. Implementation starts from that
complete commit on `feat/native-stl-fix`; it does not reinitialize or rewrite main.

The original attachment transfer was blocked by the execution environment. After
the owner uploaded the handoff to GitHub, the checkout's **42 SHA256SUMS entries
all matched** before source edits. This run does not claim a local ZIP hash check.
All 13 fixture hashes were separately verified, including every binary fixture.

A new virtual environment installed `engine/requirements.txt`. Fresh baseline:
17 original tests and 17 fixture/repair checks passed. Exact versions and full
logs are in `baseline-environment.json`, `baseline-engine-linux.txt`, and
`baseline-fixtures-linux.txt`. Historical records elsewhere in `verification/`
remain historical; they are not substituted for this run.

## Executed implementation checks

```sh
make verify PYTHON=.venv/bin/python
.venv/bin/python -m unittest discover -s tests -p 'test_smoke_tools.py' -v
.venv/bin/python engine/worker.py --self-test
bash -n scripts/build-macos.sh
.venv/bin/python -m py_compile engine/worker.py scripts/generate_notices.py scripts/smoke_bundle.py packaging/worker.spec
git diff --exit-code 8737f55 -- fixtures engine/test_stl_doctor.py
```

| Check | Actual result |
|---|---|
| Original engine tests | 17 passed |
| Worker/engine-boundary tests | 34 passed |
| Packaging smoke process orchestration (Linux, not a frozen bundle) | 7 passed |
| Real fixture audits and both rail repairs in both tolerance modes | 17/17 passed |
| Immutable fixture hashes | 13/13 passed |
| Worker dependency/geometry self-test | Passed |
| Shell syntax and Python compilation | Passed |
| Original fixtures and original engine regression file compared with handoff | Unchanged |
| macOS wheel availability | arm64 and x86_64 wheels downloaded; not runtime-tested |
| Hash-enforced macOS arm64 lock download | Passed |
| Third-party notice collection against unpacked macOS wheels | Passed for all ten distributions |

`final-python-linux.txt`, `packaging-orchestration-linux.txt`, and
`worker-self-test-linux.json` contain actual output. The seven packaging
orchestration tests were added after the full Python run and executed separately;
the `test-worker` target now discovers all 41 additional tests.
These checks used Python 3.12.14, NumPy 2.5.4, SciPy 1.18.1, Trimesh 4.12.2,
Shapely 2.2.0, and GEOS 3.14.1 on Linux x86_64.

Both defective rails repair with zero invalid pairs and unchanged bounding boxes.
Default zero tolerance preserves tiny-triangle warnings; explicit 1e-5 cleanup is
also tested. All nine healthy originals remain unchanged. Worker tests exercise
strict/bounded requests, malformed STL, incomplete scans, unsupported geometry,
filesystem failures, source changes, serialized/staged verification, candidate
cleanup, and subprocess termination.

## Native implementation and checks still requiring a Mac

> **Update:** the arm64 native build, Swift tests, packaged-helper smoke and a partial
> interactive run were later performed on a Mac and found two defects, now fixed.
> See [`macos-arm64.md`](macos-arm64.md). The text below is the original Linux record.

Swift tests cover fragmented/coalesced NDJSON, invalid streams and abnormal exits,
TERM-resistant cancellation/timeout, sequential queue and stale completion,
input identity/snapshot isolation, save state, collisions, hard-link and symlink
safety, staged/final corruption, concurrent publication, disk/permission failure,
and cleanup. **They have not been compiled or executed in this Linux environment.**

The native `.app` build, embedded interpreter/dependencies, ad-hoc signature checks,
relocated minimal-PATH helper smoke, interactive Finder/UI, accessibility, and
oldest-supported-OS checks remain pending. No architecture or minimum OS has been
runtime-certified. macOS 14 is a configured proposed floor, not a measured result.
Public signing/notarization and release were not performed or authorized.

Tracked in [deferred verification issue #1](https://github.com/Takazudo/zudo-stl-fix/issues/1).
Run on an architecture-matched Mac with Xcode and CPython 3.12.14:

```sh
swift test --package-path app
PYTHON=python3.12 bash scripts/build-macos.sh
```

Then perform `docs/ACCEPTANCE.md`'s Finder/UI checks. See `docs/BUILDING.md` for
artifact paths and the manual macOS workflow command. A new manual workflow may
need to exist on the default branch before dispatch; do not merge merely to bypass
that constraint. The available connector exposes Actions reads but no dispatch,
and the GitHub CLI Actions API route returned Forbidden even after escalation.

The managed runtime restoration and read-only context loader were rejected by
automatic approval review because protected `/root/.codex` access is prohibited.
The owner subsequently directed implementation to proceed using available tools
without retrying those paths. Bootstrap is not claimed complete. No heavy local
build was run around the unavailable guard.

## Review notes

The engine's exact predicates and conservative geometry scope remain intact.
Small changes introduce typed resource-limit errors and optional parser limits;
optional tiny-edge cleanup enumerates only existing edges, avoiding quadratic
nearby-nonedge allocation. Additional tests cover tolerance and displacement limits.

The app accepts a candidate only after a normal worker exit, a complete clean
serialized audit, matching audit/artifact hashes, and verification of private
stored bytes. Timeout/cancellation/protocol failure supersede a terminal message.
Native saving stages in a private destination-local directory, verifies bytes,
uses atomic no-replace publication, then verifies the final file. Failure cleanup
checks ownership and preserves substituted/preexisting files. Final assurance of
these native paths requires the pending Mac test run.

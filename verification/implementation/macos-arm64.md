# macOS arm64 verification — 2026-10-16 (Asia/Tokyo)

Host: macOS 26.6.2 (25G83), arm64, Xcode 27.0 (27A266a), SDK 27.0,
Apple Swift 6.4, CPython 3.12.14 (uv-managed). Deployment target 14.0 was not
runtime-tested on macOS 14; only this host OS was exercised.

## Automated results on this Mac

| Check | Result |
|---|---|
| `make test-engine` (venv, CPython 3.12.14) | 17 passed |
| `make test-worker` | 41 passed |
| `make verify-fixtures` / `verify-hashes` | 17/17, 13/13 passed |
| `engine/worker.py --self-test` | Passed (NumPy 2.5.4, SciPy 1.18.1, Trimesh 4.12.2, Shapely 2.2.0, GEOS 3.14.1) |
| `swift test --package-path app` before fixes | 54 passed |
| `swift test --package-path app` after fixes | 56 passed, real-worker test skipped without `ZUDO_WORKER_PYTHON` |
| `ZUDO_WORKER_PYTHON=.venv/bin/python swift test --filter testRealWorker` | Passed (real worker repairs `nuts-v2-40hp-double.stl` from the default temporary store) |
| `PYTHON=python3.12 bash scripts/build-macos.sh` (after fixes) | Passed: hash-locked install, PyInstaller helper, Swift tests, release build, `.app`, nested ad-hoc signature verification, relocated helper smoke (11 originals, 2 serialized candidate rechecks) |

Local archive SHA-256 (ad-hoc, not notarized, not released):
`86821b8205e6be42df82ee46d43d250c451933093252fcfa0dae5c175bb2b678  zudo-stl-fix-macos-arm64-local.zip`

## Defects found by running the real app, now fixed

1. **Every file failed** with `Job directory must not use symbolic links`.
   `URL.resolvingSymlinksInPath()` strips a leading `/private`, so the snapshot
   store under `/private/var/folders/...` was passed to the worker as the symlinked
   `/var/folders/...` path, which the worker correctly refuses. Fake-worker tests and
   an assertion using the same API missed it. Fixed with `realpath(3)`
   (`physicalDirectory`) for both the snapshot root and the export folder; tests
   now assert the physical path and run the real worker.
2. **One window per Finder-opened file.** `WindowGroup` created a new window for
   every external open event; extra windows could sit on "Preparing private
   workspace…". Replaced with a single `Window` scene.

## Interactive checks performed (relocated app, `…/アプリ テスト/zudo-stl-fix.app`)

- Launched via LaunchServices from a path containing spaces and Japanese characters;
  opened all 11 originals from a folder with a space via `open -a`.
- One window. The nine healthy originals show **No repair needed**; both
  `nuts-v2-*-double.stl` show **Repair ready** with the tiny-triangle warning
  visible; per-row **Save…** and **Save Fixed Files…** enabled only for those two
  (`macos-arm64-queue.png`).
- Quit with unsaved repairs shows the discard confirmation (`macos-arm64-quit-guard.png`).
- After force-killing the app, relaunch reaped the stale private workspace; a clean
  quit with no unsaved work removed its workspace.
- Fixture hashes 13/13 unchanged afterwards; fixtures and `engine/test_stl_doctor.py`
  are byte-identical to the handoff commit.

## Still pending (needs a person or assistive access)

This session had no Accessibility permission, so it could not click panels or keys.
Not yet exercised interactively: Finder drag-and-drop onto the window, save panel
(per-file and batch), independent re-verification of saved STLs, read-only
destination and name collisions, active/queued cancellation in the UI, Details and
JSON report export, Reveal in Finder, keyboard/VoiceOver, light appearance and
resizing, the macOS 14 floor, and x86_64. Saving, collision, permission and
cancellation logic is covered by the Swift tests above, not by UI interaction.

# x86_64 under Rosetta 2 on Apple M4: package gate and packaged-app runtime, 2026-11-08 (Asia/Tokyo)

Scope: issue #1 (x86_64 item) under epic #22. **These are x86_64 results produced
under Rosetta 2 translation on Apple silicon, not on Intel hardware.** By owner
decision on 2026-11-08, this is the accepted x86_64 evidence and a physical Intel
Mac is not required (`docs/ACCEPTANCE.md`, architecture policy). This record
does not cover macOS 14 runtime. The host runs macOS 27.0.1, and Rosetta does not
change the OS version.

## Host

| Item | Value |
|---|---|
| Machine | MacBook Air `Mac16,12`, **Apple M4**, macOS **27.0.1 (26A434)** |
| Translation | Rosetta 2 (`oahd` running). In the build shell `arch -x86_64 uname -m` = `x86_64` and `sysctl.proc_translated` = 1 |
| Xcode / SDK / Swift | 27.2 (27B52) / MacOSX 27.2 / Apple Swift 6.4.2 |
| Python | uv-managed `cpython-3.12.14-macos-x86_64-none` (`Mach-O 64-bit executable x86_64`). Under Rosetta, `platform.machine()` = `x86_64` |

BUILD-INFO's `swift --version` line shows `Target: arm64-apple-macosx27.0.0`.
That is the driver's default host target. The build itself passes
`--arch x86_64`, and every produced Mach-O file is x86_64 (see below).

## Source

Branch `verify/x86_64-rosetta-2026-11-08` @ `cc2ac93bb09203ecca3be52b96064884d760da4a`
(base `main` @ `b3d8c4e`), clean tree per BUILD-INFO
(`macos-x86_64-rosetta-m4-2026-11-08-BUILD-INFO.txt`). Compared with `b3d8c4e`, the only
production-input change is `scripts/build-macos.sh` (next section). The app and engine
sources are identical.

## Defect found and fixed: XCTests could not run under Rosetta

The first x86_64 package gate on `242d007` failed before any test ran:
`The bundle "ZudoSTLFixCoreTests" couldn't be loaded because it doesn't contain a version for the current architecture`.
SwiftPM's `swift test` lists tests with an arm64-only helper (`swiftpm-xctest-helper`),
which cannot load the x86_64 test bundle. Passing `--arch x86_64` did not help.
Running the built bundle with the x86_64 slice of Xcode's universal `xctest`
works. `build-macos.sh` now does this only when the shell is translated, and
still sets `ZUDO_WORKER_PYTHON` so the real-worker XCTest runs. Native builds
keep `swift test`. A native arm64 gate on `cc2ac93` was run to confirm this; see
"Native arm64 regression check".

## Portable checks (x86_64 venv, translated)

`arch -x86_64 <x86_64 python3.12> -m venv build/venv-x86_64`, then `pip install -r engine/requirements.txt`
(numpy 2.5.4, scipy 1.18.1, shapely 2.2.0, trimesh 4.12.2).

| Command | Result |
|---|---|
| `arch -x86_64 make PYTHON=build/venv-x86_64/bin/python test-engine test-worker verify-fixtures verify-hashes` | exit 0: 17 OK, 60 OK, 17/17, 13/13 |
| `arch -x86_64 build/venv-x86_64/bin/python engine/worker.py --self-test` | passed, `"architecture":"x86_64"`, GEOS 3.14.1, engine 1.0.0 |

## Package gate

```sh
bash "$HOME/.claude/scripts/heavy-guard.sh" -- arch -x86_64 env PYTHON=<uv cpython-3.12.14-macos-x86_64-none>/bin/python3.12 bash scripts/build-macos.sh
```

Exit **0** (`verdict=PASS`, 253 s). The lock file's hash-pinned x86_64 wheels installed
and PyInstaller froze an x86_64 helper.

| Requirement | Observed |
|---|---|
| `testRealWorkerRepairsDefectiveRailFromDefaultTemporaryStore` | **passed (3.523 s), not skipped**. The x86_64 test process ran the x86_64 build venv's `engine/worker.py` |
| Whole Swift suite | **67 executed, 0 failures, 0 skipped** (25.479 s, through `arch -x86_64 xctest`) |
| Mach-O slices | `ZudoSTLFix` `x86_64` (`minos 14.0`); `stl-worker` `x86_64`. All 136 Mach-O files in the app, including 134 `.so`/`.dylib`, are `x86_64` only |
| Signatures | nested helper and outer app `codesign --verify --deep --strict` inside the script, and again on the acceptance extraction. Ad hoc, no Team ID |
| Relocated helper smoke | `PASS relocated embedded helper: 11 originals and 2 serialized candidate rechecks` (the smoke ran the x86_64 helper translated) |
| BUILD-INFO | `cc2ac93…`, empty `git status --short`, `architecture=x86_64`, `deployment_target=14.0` |

Archive (local, ad hoc, not notarized or released):
`b3c474e919cdf82d80f6971ae8ed2fd88ca7c4bea42fcdb6ab9a0a0672ad7eb4`
(`macos-x86_64-rosetta-m4-2026-11-08-local.zip.sha256`; `shasum -a 256 -c` OK).

## Packaged-app runtime under Rosetta 2

The archive was extracted with `ditto -x -k` to
`~/zudo-accept 受入 テスト/2026-11-08 x86_64 Rosetta 受入/アプリ 置き場/zudo-stl-fix.app` and launched with
`env -i HOME=… PATH=/usr/bin:/bin open -n -a`. Inputs were copies in the same root; their
hashes equal `fixtures/originals`. Files were added through LaunchServices (`open -a <app> <files>`),
controls were pressed through the Accessibility API (`AXPress`), and state was read back
from the AX tree and the file system.

**Translation confirmed.** `ps -o flags` shows `P_TRANSLATED` (0x20000) set on both the
app (pid 76958, flags `0x34084`) and its worker (pid 76975, `0x34004`).

| Row | Observation |
|---|---|
| All 11 originals | Queue finished in about 12 s. **2 Repair ready**: `nuts-v2-40hp-double` (6 tiny-triangle warning) and `nuts-v2-60hp-double` (4). **4 Checked — review needed** ("Geometry extends below Z=0; placement unchanged"): `nuts-v3-*` and `nylon-single-v3-*`. **5 No repair needed**. This is the same split as the native arm64 records |
| Batch save | **Save Fixed Files…** saved both rails. Both rows → **Saved** with **Reveal in Finder**. The panel opened on its last-used folder (`2026-11-08 long-name 保存/保存先 out`, a test folder from the same session), and the files were saved and audited there |
| Saved bytes, independent re-audit | `nuts-v2-40hp-double-fixed.stl`: mode 0600, `PASS_WITH_WARNINGS`, 1,692 triangles, 0 invalid pairs, complete scan, bounds `[0,0,0]–[25.33876,20.132004,204]`, SHA-256 `057302f9…`, **byte-identical to the arm64 build's saved output**. `nuts-v2-60hp-double-fixed.stl`: mode 0600, `PASS_WITH_WARNINGS`, 1,676 triangles, 0 pairs, complete, bounds `…305` |
| Truncated (`raw[:len//2+7]`) | **Error**, "Worker failed: Malformed binary STL: the header declares 1694 facets (84784 bytes) but the file has 42399 bytes; it is truncated (invalid_input)" |
| Malformed (`garbage.stl`, 10,240 non-STL bytes) | **Error**, `invalid_input` (count/length mismatch) |
| Open mesh (`open-cube.stl`) | **Cannot repair safely**, "Open/nonmanifold mesh after exact cleanup; no automatic hole filling or guessed reconstruction (unsupported_geometry)" |
| Resource limit (`over-face-limit.stl`, 20,001 faces) | **Check incomplete**, "Binary STL exceeds the face limit (resource_limit)" |
| No Save on failures | Error, refused, incomplete and canceled rows offer only Details and Remove |
| Active cancellation | Four 19,040-face spheres. **Cancel** on the active `sphere-3` (Checking) terminated worker pid 83909 → **Canceled**, "Canceled; no output can be saved." The queue continued with `sphere-4` |
| Queued cancellation | `sphere-7` canceled while **Queued** → **Canceled**. It never started, and `sphere-5`/`sphere-6` finished |
| No unnecessary copies | Before quitting, the private workspace held 18 `input.stl`, 18 `report.json` and exactly **2** `candidate.stl` (the rails). No snapshot remained for error or canceled jobs |
| Quit and cleanup | A quit Apple Event exited the app and worker, and `$TMPDIR/zudo-stl-fix-<UUID>` was removed. Saved outputs remained |
| Integrity | Acceptance copies and `fixtures/originals` unchanged (`diff` of SHA-256 lists), `verify_fixtures.py --hashes-only` 13/13 |

Not repeated under Rosetta, because none of these depend on the CPU architecture
of a native SwiftUI app and they were covered natively on arm64 (`macos-m4-2026-11-08.md`):
live VoiceOver speech, contrast measurement, keyboard traversal, read-only
destinations, 10,000-name collision exhaustion, and Finder drag-and-drop. The
runtime network check was not repeated.

## Native arm64 regression check

Because `build-macos.sh` changed, the native gate was rerun on `cc2ac93`
(`PYTHON=python3.12 bash scripts/build-macos.sh`, native arm64, `proc_translated` = 0).
Exit 0 (`verdict=PASS`, 137 s). It ran `swift test`, as before: 67 executed, 0 failures.
The real-worker XCTest passed (2.023 s). The relocated smoke passed (11 originals,
2 rechecks). Archive `c047e566ab2becc6743102b342b6c6d447c224425cc8b3ce621d8b9cc0229aa5`
(local only). That BUILD-INFO lists `README.md` and `docs/DELIVERY.md` as modified,
because status-line edits for this record were in progress during the run.
No app, engine, packaging, script or fixture input differed from `cc2ac93`.

## Test-harness note

During the first batch-save attempt the app's Open panel was not frontmost. The
synthesized ⌘⇧G, ⌘V and two Return keystrokes therefore went to whichever app was
frontmost, not to zudo-stl-fix. The harness was then changed to raise the panel
and verify the frontmost process before each keystroke. Later steps avoided
keystrokes (LaunchServices open, `AXPress`, quit Apple Event). No product impact.

## Still open on #1

**macOS 14 runtime** needs a macOS 14 host. The x86_64 item is satisfied under the
amended requirement by this record.

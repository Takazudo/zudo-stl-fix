# macOS 27 / arm64-only floor: package gate and packaged-app check, 2026-11-08 (Asia/Tokyo)

Scope: owner decision of 2026-11-08 to support **macOS 27 or later on Apple silicon (arm64)
only**. It replaces the macOS 14 floor and the interim x86_64-under-Rosetta policy.
Host: MacBook Air `Mac16,12`, Apple M4, macOS 27.0.1 (26A434), native arm64
(`proc_translated` = 0), Xcode 27.2, Swift 6.4.2, CPython 3.12.14 arm64.

Source: branch `release/macos27-arm64-floor` @ `36026fb1b7b3a9819801ed05da1da0286f8d1093`,
clean tree (`macos-arm64-27-floor-2026-11-08-BUILD-INFO.txt`).

## Changes verified

| Item | Observed |
|---|---|
| Deployment target | BUILD-INFO `deployment_target=27.0`. `ZudoSTLFix` `minos 27.0` (`vtool`) |
| `LSMinimumSystemVersion` | 27.0 in both the app's and the helper's `Info.plist` (`plutil`) |
| SwiftPM platform | `swift package describe`: macos 27.0 |
| Refusal of x86_64 | `arch -x86_64 env PYTHON=<x86_64 3.12.14> bash scripts/build-macos.sh` exits 2 with "Only arm64 is supported (macOS 27 runs only on Apple silicon)." before any build step |

## Gates

- `make PYTHON=.venv/bin/python test-engine test-worker verify-fixtures verify-hashes`: 17 OK, 60 OK, 17/17, 13/13. `--self-test` passed.
- `PYTHON=python3.12 bash scripts/build-macos.sh` (heavy guard: PASS, 189 s):
  - Swift: 67 executed, 0 failures. `testRealWorkerRepairsDefectiveRailFromDefaultTemporaryStore` **passed (2.627 s), not skipped**.
  - Relocated smoke: 11 originals and 2 serialized rechecks.
  - Archive `30f24c80028013d45d6a61108c011f9cfc99e71a25adfaf5b2b0654cb7a48754` (local, ad hoc, not released).

## Packaged app on macOS 27.0.1

The archive was extracted under `~/zudo-accept 受入 テスト/2026-11-08 macOS27 floor 受入/アプリ 置き場/`, and `codesign --verify --deep --strict` returned OK. It was launched with `env -i … open -n -a` together with the 11 original copies.

- The app launched, so the 27.0 minimum is accepted on 27.0.1.
- Originals: **2 Repair ready** (`nuts-v2-*`), **4 Checked — review needed**, **5 No repair needed**.
- **Save Fixed Files…**, then Save Here: both rows → **Saved**.
  - The panel opened on its last-used folder, a test folder from this session that already held the earlier outputs. The exporter therefore chose `nuts-v2-40hp-double-fixed-2.stl` and `nuts-v2-60hp-double-fixed-2.stl` and left the existing files unchanged.
  - Re-audit: `PASS_WITH_WARNINGS`, 1,692 and 1,676 triangles, 0 invalid pairs, complete scans, mode 0600.
- A quit Apple Event exited the app and worker and removed the private workspace.
- `fixtures/originals` SHA-256 values are unchanged.

The other acceptance rows were not re-run for this change. Only the platform settings and the build script differ from `bbae4a5`. The app and engine sources are identical, and they were covered natively on macOS 27 (`macos-m4-2026-11-08.md`, #30's recheck and #35's save on `8cdcdfd`).

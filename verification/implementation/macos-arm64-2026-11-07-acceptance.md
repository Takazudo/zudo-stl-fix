# macOS arm64 interactive acceptance — 2026-11-07 (Asia/Tokyo)

Scope: issue 1 (native Finder/UI acceptance), the items feasible on one Apple Silicon
Mac. The packaging gate for the same day is in `macos-arm64-2026-11-07.md`. The
2026-10-16 record (`macos-arm64.md`) is historical.

Host: macOS 27.2 (`sw_vers` build 26B123), Apple A18 Pro, `arm64`; Xcode 27.2
(27B52), Swift 6.4.2; build CPython 3.12.14 (uv-managed). **macOS 14 and x86_64
were not exercised.**

## Apps under test

| Build | Source | Archive SHA-256 | Used for |
|---|---|---|---|
| A | `5ee4481` (merged to `main` as `8a7019d`, same build inputs) | `8662053d189ec061a15926f46ece83824dfcd16c41083c331b87dc11cf256c6c` | Initial acceptance pass, which found #19 and #20 |
| B | `8ae8222` (PR #21 candidate) | `8c6cdcfb5eaf7375302c1a0fcf826a705e8580ad1b4b938c70764fd9d8fee278` | Re-observation of the fixed behavior |

Both came from `PYTHON=<3.12.14> bash scripts/build-macos.sh`, which exited 0. In
each run the real-worker XCTest passed and was not skipped (build A: 57/57; build
B: 61/61). Each run also passed the nested and outer ad-hoc signatures and the
relocated smoke (11 originals, 2 serialized rechecks), with fixture hashes 13/13.
BUILD-INFO records each source commit with a clean tree. The archives stay local.

Each archive was extracted with `ditto -x -k` to
`~/zudo-accept 受入 テスト/アプリ 置き場/zudo-stl-fix.app`, outside the checkout, and
launched through LaunchServices with `env -i HOME=… PATH=/usr/bin:/bin open`.

## Method

Controls were driven through the macOS Accessibility API: `AXPress` on named
buttons, ⌘⇧G in the native panels, and keystrokes through System Events. Finder
drag-and-drop used real `CGEvent` mouse drags from a Finder window onto the app
window. State was read back from the app's AX tree and from window-only
screenshots. Failure cases used synthetic files or copies under
`~/zudo-accept 受入 テスト/`; the repository fixtures were never opened by the app.

## Results (observed passes, build A unless noted)

| Area | Observation |
|---|---|
| Launch / one window | Launched from the space + Japanese path. One `zudo-stl-fix` window; a private workspace `$TMPDIR/zudo-stl-fix-<UUID>` was created |
| Open panel / menu | **Choose Files…** and ⌘O (File ▸ Open STL Files…) open the "Check Files" panel; Esc dismisses it. Selecting all 11 copied originals queued all 11 |
| Eleven originals | `bar-30/40/60hp` and `nylon-double-v2-40/60hp`: **No repair needed**. `nuts-v3-40/60hp-single` and `nylon-single-v3-40/60hp`: **Checked — review needed** with "Geometry extends below Z=0; placement unchanged". Both `nuts-v2-*-double`: **Repair ready** with "6" / "4 triangles have altitude < 1e-5…" visible. Save appeared only on the two rails, and no `-fixed` copy was created for the nine others (`originals-queue.png`) |
| Finder drag-and-drop | A CGEvent drag of `same A/part.stl` onto the window queued it. A drag of `same B/part.stl` (equal basename, different folder) added a separate job: rail copy **Repair ready**, bar copy **No repair needed**, with distinct paths in the tooltip |
| Mixed drop | A multi-selection drag from `names/`: `wrong-extension.txt` was refused with "Choose a local STL file."; `レール "quoted" 'single' テスト.STL` (uppercase suffix, quotes, Japanese) became **Repair ready**; a 196-character name was accepted and truncated in the middle |
| Individual Save | **Save…** on the 40hp rail into `out ok/` wrote `nuts-v2-40hp-double-fixed.stl`; the row became **Saved** with **Reveal** |
| Read-only destination | **Save Fixed Files…** into a `chmod a-w` folder: "Save failed: Create private staging folder: Permission denied. Choose another folder or retry." Nothing was written, and the candidate stayed **Repair ready** and saveable |
| Case-insensitive collision | With `NUTS-V2-60HP-DOUBLE-FIXED.stl` present, the batch save wrote `nuts-v2-60hp-double-fixed-2.stl`. The placeholder's hash was unchanged, and **Save Fixed Files…** became disabled |
| Partial batch | Destination prefilled with `part-fixed.stl` … `part-fixed-10000.stl`. The batch saved `レール "quoted" 'single' テスト-fixed.stl` (**Saved**), while `part.stl` failed with "Could not find an available output name" and stayed **Repair ready** with Save. No staging folder or partial output remained. The 10,000-name scan took about 4 minutes on this contrived folder |
| Saved bytes, independently | `engine/stl_doctor.py check` on the saved files: both `PASS_WITH_WARNINGS`; watertight, 0 boundary/non-manifold edges, 1 shell, complete intersection scan, 0 defect pairs; slivers 6 / 4; bounds equal the manifest (`[0,0,0]–[25.33876,20.132004,204 / 305]`); 1692 / 1676 triangles |
| Details / JSON / Reveal | Details shows the status, warnings, triangles 1710 → 1692, invalid pairs 62 → 0, bounds and the no-printability disclaimer. Return closes it (default action). **Export JSON Report…** wrote `nuts-v2-40hp-double-report.json`, which contains the SHA-256 of the saved STL. **Reveal** opened Finder on `out ok/` with the saved file selected |
| Unsupported / malformed / limit | `open-cube.stl` → **Cannot repair safely**; `over-face-limit.stl` (20,001 faces) → **Check incomplete**; `garbage.stl`, `truncated.stl` → **Error**. None offered Save. In build A the reasons were missing or raw JSON (#19); build B shows them as text (`readable-reasons.png`) |
| Cancellation / queue | Four slow spheres (19,040 faces, about 5 s each) were queued through Finder open events. **Cancel** on the active and on a queued job → **Canceled** with "Canceled; no output can be saved." and no Save; the queue continued with the other two. A file added during processing was checked afterwards (**No repair needed**) |
| Quit guard | ⌘Q with unsaved repairs → "Quit and discard unsaved work?". **Keep Working** kept the app running; **Quit** exited the app and worker, removed the private workspace, and kept every saved file |
| Stale workspace | After `kill -9`, the workspace remained. The next launch reaped it and created a new one; saved outputs were untouched |
| Keyboard | With system Keyboard navigation enabled temporarily (`AppleKeyboardUIMode=2`), Tab moved the focus ring across **Advanced**, **Choose Files…** and the list. The setting was enabled only for this test |
| Accessibility names | Rows, buttons and remove buttons ("Remove <name>") have names. In build A the drop-zone label replaced the **Choose Files…** name (#20). Build B exposes `AXGroup "Drop local STL files here…"` containing `AXButton "Choose Files…"` |
| Appearance / size | Dark and light (system appearance toggled for the capture, then restored) both render correctly. Requested 300×200 clamps to the 620×468 minimum, and long names truncate in the middle (`light-min-size.png`) |
| No runtime dependency | The worker ran from `…/zudo-stl-fix.app/Contents/Helpers/STLWorker.app/Contents/MacOS/stl-worker` with `PATH=/usr/bin:/bin`. A sample taken during processing showed 0 network sockets and no loaded libraries outside the bundle or system paths |
| Fixture integrity | `make verify-hashes` 13/13 after the session |

## Defects found and fixed (PR #21, build B)

- #19: refused and incomplete rows showed no reason, and errors showed a JSON blob.
  Rows now show the worker message with its code.
- #20: the **Choose Files…** accessible name was replaced by the drop-zone label.
- The save-failure text doubled the period ("output name.. Choose"). Build B, saving
  `part.stl` into the exhausted folder again: "Save failed: Could not find an available
  output name. Choose another folder or retry." The candidate stayed **Repair ready**
  and no staging folder remained.

## Observations, not changed

- The **Advanced** disclosure's focus ring is clipped at the window's leading edge.
- Orange warning and status text has low contrast on the light background.
- Saved outputs are created with mode `0600`.
- An output folder with thousands of colliding names makes saving slow (quadratic name scan).

## Still pending

- Live VoiceOver speech. Only the AX names and roles were inspected; VoiceOver was not turned on.
- macOS 14 runtime (deployment floor), on a macOS 14 machine.
- x86_64 build and runtime, on an Intel Mac.

### Manual checklist for the pending rows

1. On each pending platform, build with `PYTHON=python3.12 bash scripts/build-macos.sh`
   and record BUILD-INFO.
2. Relocate the app to a path with spaces and non-ASCII characters, then repeat
   the table above: originals, Save/collision/read-only, cancel, quit, and stale
   workspace.
3. With VoiceOver on (⌘F5), move through the window: confirm the drop group,
   **Choose Files…**, each row's name/status/warning, and the Save/Details/Remove
   buttons are announced, and confirm the Details sheet text and Done are reachable.

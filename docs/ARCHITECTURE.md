# Architecture and packaging

## Proposed baseline

| Concern | Decision |
|---|---|
| Native application | SwiftUI, with AppKit adapters for file panels/drop integration where appropriate |
| Display name / bundle | `zudo-stl-fix` / `zudo-stl-fix.app` |
| Swift module | `ZudoSTLFix` |
| Bundle identifier | `com.takazudo.zudostlfix` as a provisional project identifier, not a registered signing identity |
| Deployment floor | macOS 14+ proposed; verify dependency and toolchain compatibility on a real Mac |
| Geometry | Existing `engine/stl_doctor.py` with its NumPy, SciPy, Trimesh, Shapely/GEOS dependencies |
| Process boundary | One short-lived worker per job; serial queue initially |
| Worker distribution | Architecture-matched Python helper frozen with PyInstaller, preferably onedir |
| Distribution | Standalone app outside the Mac App Store; signed/notarized public release is a separate gated step |

SwiftUI supplies native drag/drop APIs [S1]. Use APIs compatible with the selected deployment target; do not adopt a newer API solely because it is current. Use a small AppKit adapter if Finder behavior needs it.

This handoff does not include a SwiftUI app or a frozen worker. The decisions above are requirements/proposals, not claims of a successful macOS build.

## Responsibilities

The app owns file permissions, import snapshots, job state, process lifecycle, user-visible errors, and final save/export. A small Swift service abstraction makes the queue testable with a fake worker without claiming a fake repair is real.

The worker owns parsing, complete mesh audits, conservative repair, serialized-byte validation, and generation of a candidate plus a detailed report inside the job's private staging directory. It never receives authority to overwrite the original path or publish into arbitrary output directories.

The geometry engine is the computational baseline. Keep it importable and preserve its CLI. Add a wrapper rather than moving computational geometry into view models or reimplementing exact predicates in Swift. Any engine refactor must preserve the baseline tests and fixture results.

Use `Foundation.Process` or an equally small native subprocess wrapper. Launch with an explicit executable URL and argument array, never a shell-interpolated command. Drain stdout and stderr concurrently. Keep the UI responsive during parsing, exact intersection checks, process shutdown, and saves. No mesh work on the main actor.

## Worker lifecycle and data handling

Use the structured interface in `ENGINE-CONTRACT.md`. Match all messages to the active job ID and protocol version. Ignore stale events from canceled or superseded jobs. A ready result requires a valid final message, successful worker exit, and matching candidate hash; process exit alone is insufficient.

Terminate an active worker on cancellation/timeout, allow a short bounded grace period, then force termination if needed. Do not rely on cooperative cancellation inside the baseline exact-arithmetic loops. Test cancellation and crash cleanup before adding parallel workers.

Use private per-job directories and bounded input/report sizes. Preflight file bytes before an unbounded read, then enforce parser/face/pair limits. Baseline geometry limits are 20,000 faces and 2,000,000 candidate pairs. Suggested initial app input cap: 64 MiB; suggested job timeout: 120 seconds. Those are proposed safety defaults to benchmark, not promises about processing speed or support for every smaller file.

Keep model bytes out of logs. Do not add telemetry, runtime downloads, server calls, or analytics. Record useful local diagnostic versions/hashes and make detailed path-containing reports user-initiated. Clean canceled/failed staging directories and stale app-owned temporary data, never arbitrary paths. Keep unsaved successful candidates until clear/quit; explain loss of unsaved results when quitting. Persistent history/session recovery is not an MVP requirement.

For the first direct-distribution build, avoid taking on App Store sandboxing as an extra milestone. Still honor macOS privacy permissions, file-panel grants, and permission-denied errors; do not request Full Disk Access or administrator rights as the normal workflow. A later sandboxed build needs a separate review of file access and helper entitlements.

## Packaging work that must be proved

PyInstaller can bundle Python and dependencies for machines without a separate Python installation; its builds are platform-specific [S2]. Prove a real macOS helper early. A Linux-frozen binary is not a macOS artifact.

Use a documented onedir helper layout to ease native-library inspection. Preserve its relative runtime layout when embedding it in the app. Resolve the helper through the app bundle, not the working directory, a developer home path, PATH, `/usr/bin/python3`, or Homebrew. Choose and document a code-signing-compatible nested-code layout; do not place arbitrary executable libraries in Resources and assume signing will work.

PyInstaller supports architecture-targeted builds, but native dependency slices constrain the result [S3]. Build/test and label native arm64 and x86_64 artifacts separately as available. A tested single-architecture build is acceptable for the first milestone. Never claim universal2 or an untested architecture; do not concatenate frozen executables with `lipo` as a shortcut.

Record tested macOS dependency pins and Python/PyInstaller versions after the build. The provided Linux versions are provenance, not a verified macOS lockfile. Exercise NumPy, SciPy, Trimesh, and Shapely constrained triangulation from the **embedded** helper after moving the app away from the checkout and removing Python/Homebrew from PATH.

A local development build may be ad-hoc signed. A public Developer ID distribution needs the appropriate signing/notarization workflow [S4]. Make Team ID/certificate/notarization inputs configurable secrets, not committed values. Sign nested code deliberately, verify the complete bundle, and test the distributed artifact. No disabling Gatekeeper, blanket quarantine removal, or `sudo` as the default installation instructions. Missing credentials must not stop ordinary local implementation/tests.

See `SOURCES.md` for the cited primary documentation.

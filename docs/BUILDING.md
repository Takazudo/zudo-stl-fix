# Building and checking the native application

The source targets macOS 14. Build separately on each architecture you intend to
test. There is no universal2 product and no cross-compilation of the Python helper.
Neither a wheel download nor a successful source test proves a native app works.
Read `verification/` for actual results; the commands below are reproducible
procedures, not assertions that macOS checks have passed.

## Developer prerequisites

Use macOS, Xcode with its command-line tools selected, and CPython **3.12.14** of
the same architecture as the active shell. The app's deployment target is 14.0.
The first build downloads pinned dependencies; running the built app requires
no Python, Homebrew, terminal, account, network access, or dependency installation.

`packaging/requirements-macos.lock` pins every resolved helper/build distribution
and the SHA-256 of its macOS wheels. CPython 3.12 wheels for both arm64 and x86_64
were downloaded successfully on Linux on 2026-10-16; this establishes availability,
not runtime compatibility. NumPy 2.5.4 and SciPy 1.18.1 provide macOS 14.0 wheels
for both architectures. Shapely 2.2.0 provides arm64 11.0 / x86_64 10.13 wheels.
The remaining pins are Trimesh 4.12.2, PyInstaller 6.22.3, hooks-contrib 2026.8,
altgraph 0.17.5, macholib 1.16.4, packaging 26.3 and setuptools 84.0.0.
An available universal2 PyInstaller wheel does not make the final app universal2.

## Commands

Run these from the repository root. Heavy managed-session commands must use the
host's approved heavy-run guard when that policy applies; ordinary GitHub-hosted
CI and local development outside those managed sessions use the commands directly.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r engine/requirements.txt
make PYTHON=.venv/bin/python test-engine test-worker verify-fixtures
.venv/bin/python engine/worker.py --self-test
swift test --package-path app
PYTHON=python3.12 bash scripts/build-macos.sh
```

The last command creates a new build virtual environment, verifies pinned wheel
hashes, freezes the actual worker, runs Swift tests, builds the native executable,
creates the `.app`, generates notices and exact build provenance, verifies nested
ad-hoc signatures, and runs relocated helper smoke tests. Only after these pass
does it produce a uniquely named directory under
`build/macos-<actual-architecture>/verified.XXXXXX/` containing:

- `zudo-stl-fix.app`
- `zudo-stl-fix-macos-<actual-architecture>-local.zip`
- the archive's `.sha256` file

Each invocation gets a fresh verified directory, so prior builds cannot contribute
stale libraries to the tested app. `Contents/Resources/BUILD-INFO.txt` records
macOS, Xcode, SDK version/path, Swift, Python, installed distributions, source
commit, dirty working-tree status, actual architecture and the configured target.
Keep this evidence with the artifact. The archive is a local development artifact,
not a public release or a notarized distribution.

## Embedded helper and smoke test

The real native executable is `Contents/MacOS/ZudoSTLFix`. It resolves the helper
at `Contents/Helpers/STLWorker.app/Contents/MacOS/stl-worker`. PyInstaller's onedir
`BUNDLE` preserves its own `Contents/Frameworks` / `Contents/Resources` layout
and symlinks. Native dependencies are nested code, not loose executable libraries
hidden in the outer app's Resources. The app uses neither PATH nor a system Python
to locate the helper.

To rerun the smoke against an existing app:

```sh
.venv/bin/python scripts/smoke_bundle.py '/absolute/path/zudo-stl-fix.app'
```

The smoke copies the app to a temporary path with spaces and Japanese characters,
validates nested signatures, checks Mach-O architecture slices and rejects native
dependencies outside the bundle/system libraries. It starts the helper from that
directory with `PATH=/usr/bin:/bin`, no inherited Python variables, and a temporary
home. The smoke's developer Python only orchestrates processes; the tested worker
must use its own bundled interpreter.

`--self-test` exercises the real geometry dependencies including Shapely constrained
triangulation. The smoke then checks all eleven original fixtures, verifies that
only the two defective rails become repaired candidates with retained tiny-triangle
warnings, verifies exact staged hashes/bounds/complete intersection scans, and
starts two further worker processes to reload/revalidate those serialized outputs.
It also rechecks every original fixture hash. This tests helper packaging, not the
interactive Finder workflow or an independent geometry kernel.

## CI and manual verification

`checks.yml` runs Linux engine/worker tests, real fixtures, the self-test and build
script syntax checks on relevant pushes only. It intentionally has no duplicate
pull-request trigger. `macos.yml` is manual and builds only the selected runner's
actual architecture. Runner labels are choices, not architecture guarantees; the
build checks and artifact labels use the detected machine.

Once the manual workflow is available on the repository's default branch:

```sh
gh workflow run macos.yml --ref feat/native-stl-fix -f runner=macos-14
gh run list --workflow macos.yml
gh run watch <run-id> --exit-status
```

GitHub may not permit dispatch of a newly added workflow before it exists on the
default branch. Do not merge just to bypass that limitation; run the local Mac
commands or report native verification pending. No workflow signs with credentials,
deploys, creates a release, or changes repository protection.

Before calling the app verified, complete the interactive matrix in
`ACCEPTANCE.md`: Finder drop/open, all eleven originals, details and visible
warnings, per-file/batch save, collision/permission failures, cancellation and
queue continuation, Reveal, accessibility, appearance, resize and quit behavior.
Test the oldest offered OS on each offered architecture. Record observed results;
the deployment setting alone is not proof of macOS 14 runtime support.

## Notices and future distribution

The generated `ThirdPartyNotices` contains complete installed license/copyright
materials (including wheel-vendored GEOS/BLAS/Qhull notices), package metadata,
versions, and the Python license. Build tools are included conservatively in the
inventory. `packaging/PYTHON-LICENSE.txt` is the full file from
https://raw.githubusercontent.com/python/cpython/v3.12.14/LICENSE.
No project/model license is inferred from dependency licenses.

PyInstaller's documented macOS bundling/signing rules informed this layout:
https://pyinstaller.org/en/stable/feature-notes.html and
https://pyinstaller.org/en/stable/spec-files.html (checked 2026-10-16).

Public Developer ID signing/notarization is a separately authorized task. No
credential-based signing interface is enabled by these development scripts.
A future release workflow should accept signing identity, Team ID and notarization
profile as private configuration, sign nested code from the inside out with the
needed hardened-runtime settings, sign the outer app, notarize/staple, and test
the downloaded distribution with Gatekeeper. Review license/source obligations
for the exact shipped dependencies at that point. Never use blanket quarantine
removal, disabling Gatekeeper or administrator access as installation instructions.

# Building and checking the native application

The product supports **macOS 27 or later on Apple silicon (arm64) only** (owner
decision 2026-11-08; see `docs/ACCEPTANCE.md`). `scripts/build-macos.sh` refuses to
build on x86_64, under Rosetta, or on a host older than macOS 27. There is no
universal2 or x86_64 product.
Neither a wheel download nor a successful source test proves a native app works.
Read `verification/` for actual results; the commands below are reproducible
procedures, not assertions that macOS checks have passed.

## Developer prerequisites

Use macOS, Xcode with its command-line tools selected, and CPython **3.12.14** of
arm64, on an Apple silicon Mac running macOS 27 or later. The app's deployment target is 27.0.
The first build downloads pinned dependencies; running the built app requires
no Python, Homebrew, terminal, account, network access, or dependency installation.

`packaging/requirements-macos.lock` pins every resolved helper/build distribution
and the SHA-256 of its macOS wheels. The lock still lists x86_64 wheel
hashes from 2026-10-16; the arm64-only build installs only the arm64 wheels. The
arm64 wheels' own minimums (NumPy 2.5.4 and SciPy 1.18.1: macOS 14.0; Shapely 2.2.0:
11.0) are below the app's macOS 27 floor.
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
ad-hoc signatures, and runs relocated helper smoke tests. Its Swift test step sets
`ZUDO_WORKER_PYTHON` to that build venv's own interpreter, so
`testRealWorkerRepairsDefectiveRailFromDefaultTemporaryStore` runs the real
`engine/worker.py` instead of skipping; a plain developer `swift test` still skips
it unless `ZUDO_WORKER_PYTHON` is set. Only after these pass
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

## CI and releases

There are **no macOS GitHub Actions runners** (owner decision 2026-11-08: they cost
money). Every native build, test and release binary is made on a local Apple silicon
Mac running macOS 27 or later.

- `checks.yml` runs the Linux engine/worker tests, real fixtures, the self-test,
  build-script syntax checks and the release-asset verifier tests, on relevant pushes
  only (no duplicate pull-request trigger).
- `release.yml` runs on Linux when a GitHub Release is published (or by manual
  dispatch with a tag). It downloads the macOS archive and `.sha256` attached to that
  Release and runs `scripts/verify_release_asset.py`: checksum, version equals the
  tag, built from the tag's commit with a clean tree, arm64 executables, macOS 27.0
  minimum, bundled helper present. It builds nothing and never publishes.

### Making a release

On the local Mac, from a clean, pushed commit whose `packaging/Info.plist`
`CFBundleShortVersionString` is the new version (for example `0.1.0`):

```sh
scripts/release-macos-local.sh --upload v0.1.0
```

The script runs the full package gate (`build-macos.sh`), writes
`build/release/zudo-stl-fix-<version>-macos-arm64.zip` and its `.sha256`, verifies them,
and attaches them to the Release for the tag. If that Release does not exist yet it is
created as a **draft** at HEAD. Without `--upload` it only writes the files. On a
managed machine, wrap it in the heavy-run guard like any package gate. Review the
draft, publish it, and check that `release.yml` passes. The archive is ad hoc signed
only (no Developer ID signature or notarization), so Gatekeeper asks for
confirmation on first launch.

Before calling the app verified, complete the interactive matrix in
`ACCEPTANCE.md`: Finder drop/open, all eleven originals, details and visible
warnings, per-file/batch save, collision/permission failures, cancellation and
queue continuation, Reveal, accessibility, appearance, resize and quit behavior.
Test natively on arm64 with macOS 27 or later, the supported floor. Record
observed results.

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

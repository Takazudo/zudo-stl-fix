# zudo-stl-fix

A native macOS utility: **drop STL files → check and conservatively repair → save verified copies**.

The app uses SwiftUI/AppKit and a bundled Python helper. Processing is local; the
packaged app does not require a user Python installation, Homebrew, an account, or
a network connection. The original command-line engine remains available.

This repository contains the implementation and automated tests. **macOS build,
Finder/UI, and relocated bundled-helper verification must pass before treating
the app as verified.** See [verification/implementation](verification/implementation)
for actual results, and [docs/BUILDING.md](docs/BUILDING.md) for native build and
smoke-test commands. Download the app from
[GitHub Releases](https://github.com/Takazudo/zudo-stl-fix/releases/latest). Release
builds are ad-hoc signed only: no Developer ID signing or notarization has been performed.

Current status (2026-11-08): the packaged app has passed the native gate and
interactive acceptance, including live VoiceOver, on arm64: Apple A18 Pro
(macOS 27.2) and Apple M4 (macOS 27.0.1). Supported platform: **macOS 27 or later on Apple silicon
(arm64) only** (owner decision 2026-11-08; see [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)).
Older macOS versions and Intel/x86_64 are not supported.

## Use

Open `zudo-stl-fix.app`, drop local `.stl` files or choose **Choose
Files…**, and let the sequential queue finish. Each row shows its status and
warnings. **Details** provides audit and repair information. Save an individual
approved repair or choose **Save Fixed Files…** for the ready results, then use
**Reveal in Finder**. Healthy files do not generate redundant copies.

Original files remain unchanged. The app checks private snapshots and only offers
serialized, revalidated, hash-verified candidates. Saving uses a new name,
destination-local staging, atomic no-replace publication, and final verification.
One failed save does not prevent other ready files from being saved.

Welding defaults to zero. **Merge tiny existing edges** is an explicit advanced
option, measured in STL coordinate units. The two supplied defective rails repair
in default mode with tiny-triangle warnings retained. Negative Z remains a
placement warning; no scaling, rotation, translation, or unit conversion occurs.

Unsupported geometry is refused. Canceled, crashed, timed-out, incomplete, or
malformed worker results never enable saving. Mesh validity does not establish
printability, fit, wall thickness, strength, or source-CAD intent.

## Develop and test

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r engine/requirements.txt
make test-engine test-worker verify-fixtures verify-hashes PYTHON=.venv/bin/python
.venv/bin/python engine/worker.py --self-test
```

On a Mac with the documented toolchain:

```sh
make test-app
make package-local
```

The package script builds an actual `.app` with an architecture-matched frozen
helper, checks nested code, exercises the relocated helper, and creates a local
archive. The only product is arm64 with a macOS 27.0 deployment
target. There is no universal2 or x86_64 product. See [BUILDING](docs/BUILDING.md) for the exact Python version,
pinned dependencies, prerequisites, and remaining interactive checks.

Linux CI runs engine, worker, and fixture checks on relevant pushes only. There are no
macOS CI runners: native builds and release binaries are made on a local Apple silicon
Mac with `scripts/release-macos-local.sh`, and the Linux `release.yml` only verifies the
assets attached to a published Release. No workflow merges, publishes or signs anything.

## Command-line engine

```sh
.venv/bin/python engine/stl_doctor.py repair \
  fixtures/originals/nuts-v2-40hp-double.stl \
  fixtures/originals/nuts-v2-60hp-double.stl \
  --out-dir local-output/repaired --report local-output/repair.json
```

Default welding is disabled. Add `--weld-tolerance 0.00001` only to request tiny
existing-edge cleanup. The CLI is not the native app's transactional save
implementation.

Outputs and the JSON report never replace an input, even through a symbolic link
or hard link, and the report never replaces a repaired output. A report path like
that stops the run with exit code 2 before anything is written. An output path
like that is recorded as an error for its file (exit code 2), and the other files
continue. Without `--overwrite`, existing files are kept. With it, an unrelated
regular file is replaced by a new file through rename, keeping its permission
bits, so a link is never written through. A symbolic link at an output or report
path is refused. Repaired outputs and input hashes are checked again before and
after the report is written.

## Repository contents and provenance

| Location | Purpose |
|---|---|
| `app/` | Native application, queue, process, protocol, filesystem services, Swift tests |
| `engine/` | Existing exact-predicate engine and versioned worker adapter |
| `tests/` | Worker and engine integration tests |
| `scripts/`, `packaging/` | Native/helper build, package smoke checks, dependency pins/notices |
| `fixtures/` | 11 immutable originals, two golden references, integrity manifest |
| `reference/`, `verification/` | Historical evidence and separately labeled implementation checks |
| `docs/`, `prompts/` | Product requirements, acceptance matrix, and original implementation handoff |

Initial repository commit: `a24ea321ff56beb328cea3e5b97e2b0c75d0b1fa`.
Complete handoff commit: `8737f55dff11d72e57888c5a046245a25bad38f4`.
All 42 entries in `SHA256SUMS.txt` matched before implementation. That file records
the original handoff, including source documents subsequently edited; use
`make verify-hashes` for the immutable fixture checks in the implemented tree.

No project/model redistribution license has been selected. Bundled dependencies
retain their own licenses; local packaging collects their notices. Public
distribution and its signing/notarization review are separate work.

## Documentation

- [`doc/`](doc) is the source of the published documentation site (zudo-doc; English and Japanese). Build it with Node.js 24 and pnpm 10.30.3: `pnpm -C doc install --frozen-lockfile && pnpm -C doc build`.
- [`docs/`](docs) holds engineering specs and the development handoff. It is not published.

# zudo-stl-fix

A native macOS utility: **drop STL files → check and conservatively repair → save verified copies**.

The app uses SwiftUI/AppKit and a bundled Python helper. Processing is local; the
packaged app does not require a user Python installation, Homebrew, an account, or
a network connection. The original command-line engine remains available.

This repository contains the implementation and automated tests. **macOS build,
Finder/UI, and relocated bundled-helper verification must pass before treating
the app as verified.** See [verification/implementation](verification/implementation)
for actual results, and [docs/BUILDING.md](docs/BUILDING.md) for native build and
smoke-test commands. No public release, Developer ID signing, or notarization has
been performed.

## Use

Open the built `zudo-stl-fix.app`, drop local `.stl` files or choose **Choose
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
archive. Artifacts are labeled by the architecture built. macOS 14 is the proposed
deployment floor; an SDK setting is not evidence of testing on that OS. There is
no universal2 claim. See [BUILDING](docs/BUILDING.md) for the exact Python version,
pinned dependencies, prerequisites, and remaining interactive checks.

Linux CI runs engine, worker, and fixture checks on relevant pushes only. Native
build/helper verification is a separate manual workflow. Neither workflow merges,
releases, or deploys anything.

## Command-line engine

```sh
.venv/bin/python engine/stl_doctor.py repair \
  fixtures/originals/nuts-v2-40hp-double.stl \
  fixtures/originals/nuts-v2-60hp-double.stl \
  --out-dir local-output/repaired --report local-output/repair.json
```

Default welding is disabled. Add `--weld-tolerance 0.00001` only to request tiny
existing-edge cleanup. The CLI keeps its existing behavior and is not the native
app's transactional save implementation.

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

- [`doc/`](doc) is the source of the published documentation site (zudo-doc; English and Japanese). Build it with `pnpm -C doc install --frozen-lockfile && pnpm -C doc build`.
- [`docs/`](docs) holds engineering specs and the development handoff. It is not published.

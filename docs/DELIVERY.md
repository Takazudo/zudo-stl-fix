# Delivery plan

## Milestone 1 — Reproduce and adapt the engine

Inspect the repo; run the existing tests and fixture verifier first. Keep the original engine behavior and checksums intact. Implement a small versioned worker adapter, error mapping, bounded I/O, and adapter tests. Add a machine-readable self-test and the simplest architecture-matched helper build script.

Do an early macOS packaging spike when a Mac is available: verify the bundled native dependencies and both real repairs before investing in UI polish. On Linux, continue adapter/native-source/build-script work and report that the macOS spike is pending; do not present a Linux binary as a Mac build.

Deliverable: tested CLI/service boundary and a reproducible path to build/smoke-test the helper.

## Milestone 2 — Implement the native workflow

Create a real Xcode/Swift project using a documented, reproducible approach. The output must be an actual `.app`, not only a Swift package executable. Use native views and small services; no framework migration or geometry rewrite.

Implement drop/open input, immutable job snapshots, sequential queue, automatic conservative repair, inline status/details, cancellation, and safe save with collision handling and Reveal in Finder. Make end-to-end behavior the priority. Add explicit advanced tiny-edge cleanup only after default mode works.

Deliverable: functioning app flow and tested state/protocol/export logic.

## Milestone 3 — Harden, package and hand off

Run the acceptance matrix. Build the app with its embedded helper, test it outside the checkout, and record the exact supported OS/architecture/toolchain matrix. Resolve native library collection, code-signing layout, and runtime path issues rather than leaving a dependency on the developer environment.

Provide short developer commands for setup, engine tests, worker tests, app tests/build, helper/package smoke tests, and a local `.app`/archive. Document configurable Developer ID and notarization steps separately. Do not commit certificates, credentials, personal Team IDs, or private paths. Generate third-party notices from the dependencies actually shipped and preserve their required materials. Do not silently select a new license for the user's models.

Deliverable: real source, tests, build/package scripts, current README, a test-results summary, and a PR when permissions permit. Clearly label any remaining Mac-only verification instead of blocking unrelated completed work or fabricating a successful build.

## Lean CI proposal

Respect any existing repository policy. For a new repo, prefer one fast Linux workflow triggered by relevant source/test pushes; avoid also duplicating the same work on every PR event. Run engine/protocol tests with caching and cancel obsolete runs on the same branch. Include fixture checks when engine or fixtures change.

Provide a macOS workflow on manual dispatch for native builds and embedded-helper smoke tests. Add a release verification path only when release automation is being implemented/authorized. Heavy multi-architecture builds, notarization and full packaging should not run on every daily commit. Document how to trigger the Mac check at a milestone and before distribution.

Do not remove branch protections, spoof checks, ignore known failures, force-merge, or auto-publish. Follow the repo's branches; do not invent a `develop` branch. Merge or release only when separately authorized.

## Suggested development commands to implement

The supplied `Makefile` currently has only the working engine/fixture commands. During implementation, add real targets such as `test-worker`, `test-app`, `build-helper`, `build-app`, and `package-local`, or equivalent documented scripts. Do not leave targets that merely print success without doing the work.

A reasonable source layout adds `app/` for native code, `engine/worker.py` for the adapter, `scripts/` for builds/smoke tests, and `tests/` for protocol/export integration. Layout can change when justified; product behavior and validation guarantees cannot be silently weakened.

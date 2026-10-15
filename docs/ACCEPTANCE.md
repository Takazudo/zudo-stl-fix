# Acceptance and verification

## Existing baseline: keep it green

```bash
make test-engine
make verify-fixtures
```

The first command runs the original 17 tests. The second verifies all 13 reference files and runs the two repairs in both tolerance modes. Hashes, source dimensions, failure counts, serialized-result validity, shell count, warning behavior, and unchanged input bytes are part of the fixture checks. Do not change golden assets merely to make a test pass.

## New automated coverage required

| Area | Minimum acceptance |
|---|---|
| Import | Binary/ASCII STL; uppercase suffix; spaces, Japanese and quotes in names; malformed/truncated data; NaN/infinity; wrong extensions; mixed drops; duplicate identities; equal basenames in different folders |
| Engine/adapter | Both real defective rails fixed in default mode; warning retention; opt-in cleanup; no hard-coded geometry; valid originals unchanged; unsupported repairs refused without candidate |
| Protocol | Fragmented/coalesced stdout chunks; bounded NDJSON; malformed JSON; wrong version/job ID; excessive output; duplicate/missing terminal result; a valid-looking result followed by abnormal process exit |
| Lifecycle | Sequential queue; new drop while busy; queued/active cancellation; timeout; worker crash; app quit; no stale completion resurrecting a canceled job; next queued file still runs |
| Export | Real serialized-byte validation; staged/final hash match; writable/read-only folders; disk/write failure; collisions and case-insensitive names; input alias/hard-link safety; atomic no-replace publication; partial-batch success |
| Semantics | Warnings separate from failures; zero-Z origin unchanged; no unit inference/conversion; multiple-shell scope disclosed; resource-limited scan shown as incomplete, never clean |

Use synthetic meshes and fake worker processes to cover error cases quickly. Inject process/filesystem boundaries so tests do not need an interactive Finder session. Keep actual fixture repair tests as well; mocks are not evidence of geometry correctness.

Test every status and button transition. A canceled/failed/refused/incomplete result must not enable Save. A repaired result with warnings can be saved with warnings visible. A valid unmodified model must not produce an unnecessary candidate. Never claim "print ready" based on these checks.

## macOS smoke test: mandatory before calling the app verified

On each architecture actually offered for distribution:

1. Build the native app and frozen helper using the documented commands; record macOS, Xcode/SDK, Python, package and architecture versions.
2. Move the `.app` away from the repository/build tree to a path containing spaces/non-ASCII characters. Launch from Finder with a minimal PATH and no reliance on Homebrew or a user Python environment.
3. Drop all 11 original fixtures. Confirm the two rails produce repair-ready results and the other nine are unchanged with relevant warnings preserved. Save only approved results; independently rerun the engine verifier on the saved STLs.
4. Try a synthetic unsupported/open mesh, malformed STL, resource-limit case, same-basename files, a read-only destination, active cancellation, and adding files during processing. Confirm useful results and no partial final outputs.
5. Verify keyboard access, VoiceOver labels, system light/dark appearance, long names, small/resized windows, menu/open action, and Reveal in Finder.
6. Confirm source fixture hashes remain unchanged, the helper is truly bundled, and no runtime network request or dependency download is made. Check staging cleanup without deleting saved files.

For a public signed release, additionally verify the distributed archive/app's nested signatures, hardened-runtime behavior, notarization/stapling as appropriate, and first launch from a downloaded artifact. A development launch is not evidence that the distributed package passes Gatekeeper.

## Completion record

Record exact commands and outcomes. Distinguish: engine tests passed; protocol tests passed; Swift build passed; native UI exercised; bundled helper exercised; signing verified; public artifact notarized. Mark unperformed checks pending, not passing.

V1 implementation is complete when the real native drop/check/repair/save workflow works, test coverage exists, and a reproducible local macOS build runs without user Python setup. Public signing/notarization is not required to finish a local developer milestone without credentials, but is required before claiming the corresponding public release is ready.

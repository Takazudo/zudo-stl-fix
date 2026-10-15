# Sources and provenance

Prepared for `takazudo/zudo-stl-fix` on 2026-10-16 (Asia/Tokyo).

## Local primary evidence

- `engine/stl_doctor.py`: copied byte-for-byte from the earlier repair toolkit. This is the source of truth for existing behavior, defaults, failure semantics and scope.
- `engine/test_stl_doctor.py`: the original 17 regression tests, unchanged.
- `fixtures/originals/`: all 11 user-uploaded STLs; not rebuilt from descriptions.
- `fixtures/expected/`: the two previously generated repairs using explicit 1e-5 existing-edge cleanup.
- `fixtures/manifest.json`: hashes and historical measurements cross-checked against the provided files. Reference hashes describe particular artifacts, not the only valid triangulation of a repaired mesh.
- `reference/`: prior reports and engine documentation. Paths in those reports reflect the earlier toolkit layout; use the current fixture manifest for this repository.
- `verification/`: checks rerun while preparing this handoff. They verify the Python baseline on Linux only; no Mac app existed or was tested at this stage.

Source/reference files originate from this conversation. The user-supplied mechanical designs are not assumed to be public-domain or generally redistributable. Review visibility and rights before a public repository/release; do not contact external services with model data during runtime.

## External primary documentation, checked 2026-10-16

[S1] Apple — SwiftUI drag and drop / drop destination API.
https://developer.apple.com/documentation/swiftui/drag-and-drop
https://developer.apple.com/documentation/swiftui/view/dropdestination(for:action:istargeted:)
Used to establish the native input mechanism; choose APIs available at the declared deployment target during implementation.

[S2] PyInstaller — operation and platform-specific output.
https://pyinstaller.org/en/stable/operating-mode.html
Used for the bundled-interpreter approach and requirement to build for the target platform. Packaging remains work to implement and test.

[S3] PyInstaller — macOS architectures, native binary validation and signing.
https://pyinstaller.org/en/stable/feature-notes.html
Used for architecture-matched helper builds and native dependency/signing risks. Do not assume universal2 compatibility from a Python package name.

[S4] Apple — Developer ID distribution and notarization.
https://developer.apple.com/developer-id/
https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
Used to separate local developer builds from signed/notarized public distribution.

The native stack, macOS 14 development floor, proposed caps, queue policy, UI layout and CI cadence are project decisions, not measured properties of an existing app. Current deployment floors, supported package versions and signing requirements must be rechecked when implementing/releasing.

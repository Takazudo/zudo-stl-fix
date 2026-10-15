# Development instructions

Project: **zudo-stl-fix**. Intended repository: **takazudo/zudo-stl-fix**.

## Product and implementation

Build the real, small macOS drag-and-drop app specified in `docs/PRODUCT.md`. Use a native SwiftUI UI with AppKit where needed and the existing Python geometry engine in a separate bundled helper process. Keep the CLI usable. Do not introduce Electron, a web server, cloud processing, accounts, analytics, a 3D editor, or a new geometry kernel for the MVP.

Inspect existing repository files and instructions before editing. This handoff is not permission to overwrite unrelated work, force-push, change repository visibility, alter branch protections, create a remote repository, or release publicly. The owner creates the repository.

## Invariants

- Original STLs and golden fixtures are immutable inputs. Never replace them.
- Repair scope is conservative. Unsupported is an expected outcome, not a reason to guess a solid.
- A validated mesh is not proof of printability, fit, wall thickness, strength, or design intent.
- Do not silently scale, rotate, translate, smooth, voxelize, fill arbitrary holes, or weld nearby walls.
- Default weld tolerance is zero. Any optional existing-edge collapse must be explicit and reported.
- Revalidate serialized STL coordinates before presenting a repair as ready. Verify stored bytes match those validated.
- Timeout, cancellation, process failure, resource limit, truncated protocol, or uncompleted scan must never become success.
- Healthy inputs create no unnecessary `-fixed` copies. Warnings are visible and distinct from failures.
- Keep exact predicates and existing safety checks unless a tested change justifies a replacement.

## Implementation discipline

The current `engine/stl_doctor.py` and `engine/test_stl_doctor.py` are the baseline, not a finished GUI backend. Add a tested structured worker adapter; do not scrape CLI text. Do not call the CLI's nontransactional output helper as the production save implementation. Prefer small adapters to an early rewrite.

Run `make test-engine` and `make verify-fixtures` before and after engine changes. Add tests for the actual app behavior you implement. Preserve the original fixture hashes and record dependency versions. Never substitute hard-coded file names, face indices, pre-repaired fixtures, or a topology-only test for real repair and intersection validation.

On non-macOS hosts, implement and test everything available: engine adapter, protocol, cancellation controller design, native source, build automation, and non-UI tests. Record macOS compilation/runtime/package tests as pending when they were not run. Do not abandon all work because Xcode or signing credentials are unavailable; do not fabricate screenshots, builds, or test results.

## Development flow

Keep changes reviewable and CI inexpensive. Follow an existing branching model; otherwise use one short-lived feature branch from the repository's default branch. Do not add `develop` or multiple release branches without need. Do not weaken existing required checks.

Default proposal: fast engine/protocol tests on one Linux push workflow with path filters; macOS app builds and bundled-helper smoke tests by manual dispatch, plus release verification when a release is actually requested. Avoid duplicate push/PR builds and repeated heavyweight builds per commit. A failed check is still actionable; "low CI" does not mean reporting known failures as green.

Implement through the requested milestone, test it, commit it, and open a PR when repository access allows. Do not auto-merge or publish releases unless separately authorized. Report exactly what works, what was tested, the build commands, and the concrete remaining macOS-only checks.

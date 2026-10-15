# Implement zudo-stl-fix

You are working in **takazudo/zudo-stl-fix**, the owner's personal GitHub repository. Build a real, simple macOS app named **zudo-stl-fix**. The owner has supplied this development handoff at the repository root. Inspect the actual checkout and any existing instructions before editing; preserve unrelated work. The repository is already the development destination—do not create another remote repository.

## Start with the supplied assets

Read `AGENTS.md`, `README.md`, and `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/ENGINE-CONTRACT.md`, `docs/ACCEPTANCE.md`, and `docs/DELIVERY.md`. Inspect `engine/stl_doctor.py` and its tests. Read `fixtures/manifest.json` and the prior repair reports when needed.

Set up the engine dependencies, run `make test-engine` and `make verify-fixtures`, and record the baseline. There are 11 original STL fixtures and two repaired references. Both original nuts-v2 double rails have 62 invalid triangle-pair interactions; the other nine originals pass the implemented mesh checks with relevant warnings. The supplied fixture verifier exercises repairs with tolerance zero and 1e-5. Do not replace actual repair with canned output, hard-coded filenames, face indices, or a topology-only check.

## Product to implement

One small native window with a large drop target, a Choose Files action, a per-file queue, concise status/details, cancellation, Save Fixed Files, and Reveal in Finder.

The default flow is **drop one or several STL files → automatically validate and conservatively repair → save verified copies to a selected folder**. Everything runs locally. No terminal, Python installation, dependency download, account, network upload, or telemetry for end users.

Use a native SwiftUI front end with AppKit where necessary, plus the existing Python engine as a bundled subprocess helper. Do not rewrite the geometry kernel or introduce Electron, a web server, a 3D editor, generalized remeshing, or slicer features. Use macOS 14+ as the proposed initial deployment target; verify the real build requirements. Do not assume the owner's CPU architecture. Build and label each architecture actually tested.

## Essential safety and behavior

Originals are immutable. Work on private job snapshots. Process the queue off the main thread, sequentially initially. Do not create redundant output for healthy models. Distinguish no-repair-needed, repair-ready, saved, warnings/review-needed, unsupported repair, incomplete scan, cancellation, and operational failure.

Default weld tolerance is **0**. The two defective rails should repair successfully in that mode while retaining tiny-triangle warnings. Offer tiny existing-edge cleanup only as an explicit advanced option, with tolerance in STL coordinate units and measured displacement in the report. Never silently scale, rotate, translate, smooth, voxelize, fill unknown holes, or weld opposing walls. Below-zero Z is a placement warning, not a reason to clip or move a part.

Revalidate serialized STL coordinates before accepting a candidate and confirm written bytes match. A timeout, resource limit, worker crash, unfinished scan, or unsupported repair must never be shown as a successful fix. Keep the existing engine's conservative refusal behavior. Mesh validity is not proof of printability or hardware fit.

Save through native folder selection with collision-safe names, atomic no-replace publication and final hash verification. Never overwrite any source, existing destination, or input alias/hard link. Allow saving successful files from a mixed-result batch. Handle malformed files, spaces/Unicode in paths, duplicate basenames, permissions, interrupted writes, cancellation and process failures gracefully.

## Implementation expectations

Add a small, versioned JSON/NDJSON worker adapter around the importable engine; follow `docs/ENGINE-CONTRACT.md`. Do not scrape CLI console text or treat its current file writer as the transactional GUI save path. Separate queue, process, geometry and export responsibilities and test their boundaries. Preserve the CLI and existing tests.

Package the helper, interpreter and native dependencies inside `zudo-stl-fix.app`; use a reproducible architecture-matched PyInstaller build and a native app build. Prove helper packaging early on macOS. The shipping app must run away from the checkout without system/Homebrew Python. Provide real build/test/package scripts and record tested dependencies, architectures and minimum OS. Do not claim universal2 without validating every dependency slice.

Implement through the milestones in `docs/DELIVERY.md`; do not stop after making a plan, issue list or empty scaffold. Keep CI lean: fast Linux engine/protocol checks on relevant changes, macOS build/helper smoke checks by manual dispatch and at release milestones; avoid redundant heavy push/PR pipelines. Follow existing branches and protections rather than creating an elaborate flow.

Add the automated and native smoke coverage in `docs/ACCEPTANCE.md`. On a Linux-only agent, continue all implementable source, protocol, tests and build automation work. Clearly mark macOS compilation/runtime/package verification as pending and provide exact runnable commands. Missing Xcode or signing credentials is not a reason to abandon the implementation, and it is not permission to claim Mac testing happened. Local builds and optional public signing/notarization are separate milestones; never disable macOS security as the default installation workaround.

Finish with working code, tests, build/package instructions, a truthful verification summary, and a commit/PR when repository access permits. Do not auto-merge, change protections/visibility, publish a release, or use signing credentials without authorization. Report the runnable commands, tested behavior and concrete remaining macOS-only checks. Start by inspecting the repository and reproducing the baseline, then proceed into implementation without another approval round for routine technical decisions.

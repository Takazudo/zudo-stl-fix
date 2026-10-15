# zudo-stl-fix

**A small macOS utility: drop STL files, repair supported mesh defects, save verified copies.**

Intended repository: `takazudo/zudo-stl-fix` (the owner's personal GitHub namespace).
Application display name and release bundle: `zudo-stl-fix` / `zudo-stl-fix.app`.

## Handoff status

This is a **development handoff, not an implemented or compiled macOS app**. It contains the existing Python repair engine, its regression suite, real input/output fixtures, fresh verification results, product and engineering requirements, and an implementation prompt. The native UI, worker adapter, macOS packaging, and app-level tests are work for the implementation agent.

The original engine and its original tests are copied without modification. The fixture verification script and development documents are new. No repository has been created, uploaded to, or modified by preparing this bundle.

## Start development

Create `takazudo/zudo-stl-fix`, then put the contents of this directory at the repository root, preserving any files you already added. Do not create a second nested `zudo-stl-fix` directory. Review the included user-supplied models before making the repository public.

Give your development agent `prompts/CODEX-IMPLEMENTATION.md`. It directs the agent to implement the app rather than stop after producing another plan.

Read these documents in order:

1. `docs/PRODUCT.md` — interaction, scope, and safe behavior.
2. `docs/ARCHITECTURE.md` — native shell, worker, and packaging decisions.
3. `docs/ENGINE-CONTRACT.md` — baseline API, limitations, and proposed worker interface.
4. `docs/ACCEPTANCE.md` and `docs/DELIVERY.md` — required tests and implementation sequence.

`AGENTS.md` contains repository-wide development guardrails. `docs/SOURCES.md` distinguishes source-code evidence, previously measured results, current verification, and external platform documentation.

## Run the existing engine

These are developer commands. The finished app must not ask end users to install Python.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r engine/requirements.txt
make test-engine
make verify-fixtures
```

`make verify-fixtures` audits all 11 original models and both repaired reference models, then repeats the two repairs with welding disabled and enabled. `make verify-hashes` checks the supplied file hashes without third-party dependencies.

Existing command-line repair:

```bash
python engine/stl_doctor.py repair \
  fixtures/originals/nuts-v2-40hp-double.stl \
  fixtures/originals/nuts-v2-60hp-double.stl \
  --out-dir ./local-output/repaired \
  --report ./local-output/repair.json
```

That is conservative mode: no approximate welding. To reproduce the earlier tiny-edge cleanup too, use `--weld-tolerance 0.00001` and a new output/report destination. Tolerances are in the original STL coordinate units; the file does not specify a physical unit. The CLI refuses existing destinations by default.

## Included assets

| Location | Contents |
|---|---|
| `engine/` | Unmodified `stl_doctor.py`, 17 original tests, dependency ranges |
| `fixtures/originals/` | All 11 original uploaded STL files |
| `fixtures/expected/` | Two previously repaired STL references |
| `fixtures/manifest.json` | SHA-256 hashes, dimensions, status and repair expectations |
| `reference/` | Prior validation reports, repair report, original engine README and environment |
| `scripts/verify_fixtures.py` | New portable fixture and repair verifier |
| `verification/` | Fresh checks from this handoff's Linux environment |
| `docs/`, `prompts/` | App specification and ready-to-use implementation prompt |

The fresh verification includes **17 original regression tests passed** plus **17 fixture/repair checks passed**: 13 fixture audits and four repair-mode runs. These are not macOS UI, packaging, signing, or printing tests. See `verification/README.md`.

## Product boundaries

Reuse the existing conservative geometry engine. This is not a universal mesh-repair application, CAD editor, slicer, or printability certificate. Default to local-only processing, no automatic geometry scaling or placement changes, no original-file replacement, and no successful result from an incomplete validation.

Proposed development target: macOS 14 or newer. This is a project default, not a claim about the owner's Mac or a tested deployment floor. Build and label architecture-specific artifacts; do not assume whether the owner uses Intel or Apple Silicon.

No license has been chosen for the new project. Preserve third-party notices and document bundled dependencies before distributing an app. Inclusion of user-supplied models does not grant a general redistribution license.

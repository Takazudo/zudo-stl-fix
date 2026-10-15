# Real STL regression fixtures

`originals/` contains all 11 original user uploads. `expected/` contains the two previously repaired double-rail models. Do not edit these files during implementation.

`manifest.json` records their exact SHA-256 hashes and expected audit measurements. Both original `nuts-v2` doubles fail intersection validation (62 invalid pairs each); the other nine have no mesh failures, although four v3 models carry negative-Z placement warnings. Expected repairs use explicitly enabled tiny-edge cleanup at 1e-5 coordinate units.

The app defaults to zero tolerance. Its successful default rail repairs intentionally retain the tiny-triangle warnings. The verifier checks both default and opt-in modes.

Checksums protect these particular fixtures. Future valid repair output may differ in face ordering or triangulation bytes; compare geometry, validation results, boundaries and numeric guards rather than forcing the output to equal a golden binary. Production code must never identify a fixture name and return its precomputed repaired file.

Run `python scripts/verify_fixtures.py --hashes-only` from the repository root for asset integrity alone, or `make verify-fixtures` for complete geometry and repair verification. The models are user-supplied designs, not automatically licensed for redistribution.

# Existing geometry engine

`stl_doctor.py` preserves the preceding toolkit's geometry predicates and CLI.
`test_stl_doctor.py` is the unchanged original regression suite. The native app
uses `worker.py`, a bounded v1 NDJSON adapter; it does not parse CLI output or use
the CLI's file writer for final saves. Implementation changes add typed resource
limits, bounded parsing, and existing-edge enumeration for optional cleanup.

From repository root:

```bash
python -m pip install -r engine/requirements.txt
make test-engine
make test-worker
make verify-fixtures
python engine/worker.py --self-test
```

Use `python engine/stl_doctor.py --help` for CLI options. The original standalone README is at `../reference/engine-original-README.md`; its relative paths refer to the old toolkit. The current app integration design is `../docs/ENGINE-CONTRACT.md`.

Dependency ranges here are the supplied engine requirements. `../reference/requirements-tested-original-linux.txt` records the historical environment, not a macOS lock. Implementation should add tested, architecture-appropriate build locks without confusing a Linux version record with Mac compatibility.

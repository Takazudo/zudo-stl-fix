# Existing geometry engine

`stl_doctor.py` and `test_stl_doctor.py` are unchanged copies from the preceding STL repair toolkit. The engine is working code; no app worker adapter is implemented yet.

From repository root:

```bash
python -m pip install -r engine/requirements.txt
make test-engine
make verify-fixtures
```

Use `python engine/stl_doctor.py --help` for CLI options. The original standalone README is at `../reference/engine-original-README.md`; its relative paths refer to the old toolkit. The current app integration design is `../docs/ENGINE-CONTRACT.md`.

Dependency ranges here are the supplied engine requirements. `../reference/requirements-tested-original-linux.txt` records the historical environment, not a macOS lock. Implementation should add tested, architecture-appropriate build locks without confusing a Linux version record with Mac compatibility.

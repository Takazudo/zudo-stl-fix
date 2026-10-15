# Engine integration contract

## Existing implementation — verified from the supplied source

`engine/stl_doctor.py` version 1.0.0 is an existing CLI/importable module, not the worker protocol described below.

Useful entry points:

```python
stl = load_stl(path)                         # STL dataclass: mesh, normals, raw, format
before = audit(stl, max_faces=20000, max_pairs=2000000)
raw, after, details = repair(
    stl, before, weld_tolerance=0.0,
    max_faces=20000, max_pairs=2000000,
)
```

`audit()` returns status `PASS`, `PASS_WITH_WARNINGS`, or `FAIL`; explicit `failures` and `warnings`; dimensions/bounds; hashes; topology results; and `surface_intersections.defect_pair_count` with detailed records. A complete intersection scan matters: watertight connectivity alone is not enough.

`repair()` removes exact duplicate/degenerate faces where safe, fixes a supported single shell's orientation, and retriangulates suitable exactly planar folded/overlapping patches from their existing oriented boundaries. It can optionally collapse short existing edges. It serializes binary STL, reloads and audits those coordinates, and applies shell-count, bounds, and relative algebraic-volume guards before returning bytes. It raises `UnsafeRepair` when a candidate cannot be validated conservatively.

Default welding is disabled. Negative Z coordinates and tiny triangles can remain warnings. ASCII decimals are first parsed as binary64; binary output uses float32. Preserve and surface the reported export quantization rather than promising all ASCII coordinates are unchanged.

The current CLI uses text stdout, batch JSON reports, and exit codes 0 (success/warnings), 1 (mesh failure/refusal), and 2 (operational error/limit). **It is not a streaming JSON service.** Do not parse its human stdout as an API. Its output helper is not a transactional app-save implementation.

The baseline does not automatically repair open/nonmanifold meshes after exact cleanup, unresolved general noncoplanar intersections, invalid/branching patch boundaries, or multiple/nested shells. These are deliberate scope limits. A stopped/resource-limited scan is not a valid clean scan. The broad phase has quadratic worst-case behavior, so respect bounded work.

## Proposed app worker v1 — TO IMPLEMENT

Launch one helper per job. Send one size-bounded JSON request on stdin and close stdin. The helper emits UTF-8 newline-delimited JSON on stdout; diagnostic text goes only to stderr. Introduce a protocol version independent of the engine version. Add a `--self-test` or equivalent build-smoke command.

Request fields:

```json
{
  "protocol_version": 1,
  "job_id": "a-generated-UUID",
  "operation": "check_and_repair",
  "input_path": "/private/job/input.stl",
  "staging_directory": "/private/job",
  "options": {
    "weld_tolerance": 0.0,
    "max_faces": 20000,
    "max_pairs": 2000000
  }
}
```

The paths above are illustrative, not literal runtime paths. The app creates the directory and source snapshot. Validate that worker artifacts are regular files inside that job directory. Reject symlinks, path traversal, unknown protocol versions/operations, nonfinite values, and invalid resource limits.

Every event contains `protocol_version`, `job_id`, and `event`. Events may be `started`, `progress`, and exactly one terminal `result`. Progress has a `phase` and human-readable message; omit percent rather than inventing one. A malformed or excessive stdout stream is a protocol error, not a successful repair.

Terminal results include:

| Field | Required meaning |
|---|---|
| `outcome` | `unchanged`, `repaired`, `refused`, `incomplete`, or `error` |
| `validation_status` | Actual final audit status, or null when no complete audit exists |
| `summary` | Available before/after dimensions, counts, topology, and displacement metrics |
| `warnings` | Readable warnings plus stable identifiers where available |
| `candidate` | For `repaired` only: relative path, SHA-256 and byte size of verified staged STL |
| `report` | Optional detailed JSON report relative path, hash and byte size |
| `error` | When applicable: stable code and human-readable explanation |

Error codes should separate `unsupported_geometry`, `invalid_input`, `resource_limit`, `timeout`, `permission_denied`, `input_changed`, `verification_failed`, `protocol_error`, and `worker_crashed`. Do not infer app success solely from exit code or the presence of a file. Map the baseline's errors deliberately; add small typed exceptions/codes when necessary instead of relying on untested English substring matching.

Protocol exit convention: 0 with a valid terminal result for completed domain outcomes (`unchanged`, `repaired`, `refused`, `incomplete`); nonzero for operational/protocol failure. An error result may precede nonzero exit. Cancellation and abrupt termination may have no terminal event; the app owns those terminal states. Do not confuse these rules with the existing CLI exit convention.

## Operation sequence and export authority

1. Read only the private input snapshot; parse without silent mesh processing/welding. Record its hash.
2. Run complete validation. Do not call `repair()` unnecessarily: mirror the CLI's `needs_work` decision, including invalid normals and explicitly requested tiny-edge cleanup.
3. Return `unchanged` for a completed check without supported work. Keep warnings visible; do not generate an STL copy.
4. Attempt supported repair with the requested, recorded tolerance. Refusal emits no candidate.
5. Fully validate serialized coordinates before approving bytes. Write into private staging and verify the written bytes equal the approved bytes/hash. Clean invalid/partial candidates on failure.
6. Emit the terminal result only after that verification. The native app checks the artifact, result, and process status, then offers saving through its own no-overwrite transactional path.

The native app, not the helper, chooses final user destinations. Neither `--overwrite` nor arbitrary destination paths from the worker are exposed as app repair options.

## Reference expectations

Both original `nuts-v2-*-double.stl` files contain 62 invalid triangle-pair interactions; the other nine originals have no mesh failures under the performed checks. With welding disabled, both rail repairs reach zero invalid pairs and unchanged bounding boxes, retaining tiny-triangle warnings. With welding at 1e-5, expected outputs have 1,686 and 1,672 triangles respectively and no tiny-triangle warnings.

Use `fixtures/manifest.json` and `scripts/verify_fixtures.py`, not these two filenames inside production repair logic. Reference hashes protect fixtures; new repair exports need geometric/invariant comparisons rather than byte-identical triangulation ordering. No claim that a prior validator with the same algorithm lineage is an independent geometry kernel.

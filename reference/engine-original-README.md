# STL Doctor — repaired rails and reusable validation/repair script

## Supplied repaired files

- `fixed/nuts-v2-40hp-double-fixed.stl`
- `fixed/nuts-v2-60hp-double-fixed.stl`

Both files pass the checks on the **actual exported binary STL bytes**: no invalid
triangle intersections/contacts, closed edge and vertex topology, one connected
shell, consistent winding, positive signed volume, valid stored normals, no exact
duplicate faces, and no exactly zero-area triangles. Overall bounds are unchanged.
The very small triangles identified in the original report were also removed.

All 11 original uploads were left unchanged. Only the two defective files have
repaired outputs in this package. The v3 files' negative-Z placement was not changed.

See `REPAIR-SUMMARY.md` for measurements and `repair-report.json` for detailed
before/after results, affected face indices, cleanup tolerances, and file hashes.

## Installation

Use Python 3.10 or newer. From this folder, on macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate with `.venv\Scripts\activate` instead. The script was executed
and tested on Linux with Python 3.13.5. It was not separately executed on macOS or
Windows; all dependencies are ordinary Python packages. `requirements-tested.txt`
records the exact package versions used here. Use the broader `requirements.txt`
for compatible releases on a different supported Python version.

No account, API key, cloud upload, external program, or network access is required
to run the script after its dependencies are installed.

## Verify the supplied files

```sh
python stl_doctor.py check ./fixed --report my-verification.json
```

Both should pass. The tool refuses to replace an existing report unless you use
`--overwrite`, so use a fresh report name for repeated runs.

## Check your own STLs

Place the original files in an `input` directory, then run:

```sh
python stl_doctor.py check ./input --report check-report.json
```

You can also pass multiple filenames or a quoted glob such as `"./input/*.stl"`.
Directory scanning is non-recursive. Both binary and ordinary line-oriented ASCII
STL are supported. Units remain whatever the input uses; no millimeter assumption
is built into the geometry operations.

## Repair the same defects as these rail files

To reproduce the supplied repairs, put the original two nuts-v2 files in `input`:

```sh
python stl_doctor.py repair "./input/nuts-v2-*-double.stl" \
  --weld-tolerance 0.00001 \
  --out-dir ./repaired \
  --report repair-run.json
```

Successful results are named `<original-stem>-fixed.stl`. A valid original that
needs no selected repair is left alone and does not generate a redundant copy.

The `--weld-tolerance 0.00001` option is **explicitly opt-in**, in input coordinate
units. It collapses only very short existing mesh edges; it does not merge arbitrary
nearby surfaces across gaps. In these files it merges three near-identical vertices
in the 40hp model and two in the 60hp model, removing six and four tiny triangles.
The largest displacement is 0.0000026974 coordinate units, below the chosen limit.
This setting could remove an intentional feature below that size in other models;
choose a tolerance appropriate to the input scale.

To repair planar overlaps **without any tolerance-based vertex changes**, omit
that option:

```sh
python stl_doctor.py repair "./input/nuts-v2-*-double.stl" \
  --out-dir ./exact-only \
  --report exact-only-report.json
```

The exact-only route resolves these files' wall intersections but intentionally
leaves the original tiny-edge/sliver warnings. It uses existing coordinates only.

## What the detector checks

The script reads the STL without silent geometry cleanup. Identical coordinates
are indexed exactly, not rounded together. It checks file parsing, finite vertex
coordinates, boundary/nonmanifold edges, closed vertex links, shell count, winding,
signed volume, exact duplicate and zero-area faces, stored normals, tiny triangle
altitudes, and Z placement.

The intersection pass tests every AABB-overlapping triangle pair using integer and
rational predicates. It detects coplanar overlap/foldback, noncoplanar crossings,
and unexpected contacts. Legitimate shared topological edges/vertices are excluded.
Zero-area triangles are separate failures and are not treated as valid planes.
Binary input predicates are exact for the stored float32 values. ASCII decimals
are first parsed as binary64 values; the exact predicates apply to those parsed
values, not arbitrary-precision decimal source text. Shape metrics are floating-point.

## What the fixer does—and refuses to do

The automatic repair path supports **one closed shell**, with these operations:

1. Remove exact duplicate and exactly zero-area faces when the remaining topology
   is valid, and correct face winding/orientation for a single closed shell.
2. Detect affected, edge-connected, **exactly coplanar** patches; derive their
   oriented boundary loops; preserve valid holes; and retriangulate while reusing
   the original boundary coordinates. Each patch must preserve every directed
   boundary edge, exact signed projected area, and exact algebraic volume.
3. Optionally collapse very short existing edges at the explicit weld tolerance.
4. Regenerate normals, serialize binary STL, reload and revalidate those exact
   bytes, and check shell count, bounds change, and relative signed-volume change
   before writing a fixed output. The relative volume-change guard is 1e-6.

This is not a universal repair engine. It refuses unsupported open/nonmanifold
surfaces, branching/invalid patch boundaries, unresolved noncoplanar intersections,
and repairs involving multiple/nested shells. It never guesses missing surfaces,
fills holes indiscriminately, voxel-remeshes, smooths, rescales, reorients the part
for printing, or translates the object onto a bed. Unsupported candidates are
reported as `REFUSED`, without writing a new fixed STL for that file.

A check can warn about multiple shells without automatically reorienting cavity
shells. Their containment and intended inside/outside semantics are not certified.

## Safety, reports and batch use

Input files are never overwritten, including with `--overwrite`. That flag permits
replacement of destination outputs and the JSON report only. An existing output
is otherwise an error. Files with duplicate basenames in different directories
must be processed into separate output folders.

JSON reports include original/output SHA-256 hashes, dimensions, topology results,
intersection pair counts and face IDs, repair operations, tolerances, and warnings.
Patch face IDs refer to the cleaned/oriented pre-patch stage; for these two original
files the initial cleanup and orientation did not change face order.

Exit codes are `0` for successful checks/repairs (warnings allowed), `1` for detected
mesh failures or a refused repair, and `2` for malformed input, a scan resource
limit, file-system problems, missing dependencies, or other operational errors.

The broad phase has quadratic worst-case cost. Defaults are 20,000 faces and
2,000,000 candidate pairs per file. `--max-faces` and `--max-pairs` can raise those
limits, at the cost of runtime/memory. A limit or incomplete scan is an error,
**never a clean result**. This implementation targets small/medium engineering
STLs, not production-scale scans with millions of triangles.

## Tests and cross-checks

```sh
python -m unittest -v test_stl_doctor.py
```

The 17 regression tests cover valid meshes, planar foldback, a non-axis-aligned
patch, preservation of a patch hole, winding reversal, duplicates, zero-area
faces, open meshes, intersecting shells, nonmanifold point contacts, unresolved
single-shell noncoplanar intersections, optional tiny-edge cleanup, ASCII/binary
I/O, malformed data, scan limits, original preservation, and output refusal.

`originals-validation.json` reproduces the original two failures (62 invalid
triangle pairs each) and nine passing meshes (four with placement warnings).
`fixed-validation.json` contains a separate run over the saved repaired STLs.
`prior-validator-cross-check.json` repeats the checks with the read-only validator
from the previous response, included as `prior_validate_stls.py`. It shares the
same predicate lineage, so this is a regression cross-check, not an independent
CAD-kernel certification. That prior script accepts binary STL only and has fewer
input/resource safeguards than `stl_doctor.py`.

## Limits of the result

These are mesh-integrity repairs, not source-CAD or manufacturing certification.
Hardware fit, intended dimensions, wall thickness, strength, print orientation,
build-volume fit, material behavior, and sliced layers still need review.
A passing mesh does not establish that the design is mechanically correct.

## Implementation references

- Shapely constrained triangulation (preserves polygon boundary edges):
  https://shapely.readthedocs.io/en/latest/reference/shapely.constrained_delaunay_triangles.html
- Trimesh winding/normal repair:
  https://trimesh.org/trimesh.repair.html

Dependencies are installed separately and retain their own licenses. No third-party
binary packages or font files are bundled.

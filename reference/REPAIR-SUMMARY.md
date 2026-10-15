# Repair summary

Both repaired STLs pass the geometric/topological checks on their exported binary bytes. Original files were not modified.

## Measured results

All dimensions and tolerances below are in STL coordinate units. Millimeters are an import assumption, not an encoded STL unit.

| Check | 40hp double | 60hp double |
|---|---:|---:|
| Invalid triangle pairs | 62 → 0 | 62 → 0 |
| Triangles | 1710 → 1686 | 1694 → 1672 |
| Triangles with altitude < 1e-5 | 6 → 0 | 4 → 0 |
| Connected shells after repair | 1 | 1 |
| Open / nonmanifold edges after repair | 0 / 0 | 0 / 0 |
| Nonmanifold vertices after repair | 0 | 0 |
| Exact duplicate / zero-area triangles after repair | 0 / 0 | 0 / 0 |
| Overall X × Y × Z | 25.338760376 × 20.132003784 × 204.000000000 | 25.338760376 × 20.132003784 × 305.000000000 |
| Maximum overall-bounds change | 0 | 0 |
| Maximum tiny-edge vertex displacement | 2.6973983047e-06 | 1.12268025987e-08 |
| Vertices merged | 3 | 2 |
| Relative algebraic-volume change | 2.58718027287e-12 | 1.22938978749e-15 |
| Original triangles retained exactly, including orientation | 1,673 / 1,710 | 1,662 / 1,694 |

## What changed

Each defective wall patch contained 24 triangles. The repair replaced these with six triangles covering the valid oriented boundary, preserving all eight boundary vertices and all eight directed boundary segments. The repaired wall lies at X = 10.528121948242188, between Y = 6.201499938964844 and Y = 8.201652526855469, over the full length of each rail. The extraneous overlapping/folded portions below that boundary were removed; the surrounding valid wall is not guessed from a new shape.

This planar repair introduces no new vertex coordinates and preserves the patch’s exact signed area and algebraic volume. The apparent decrease in total summed triangle area is expected: the defective files counted overlapping surface area multiple times.

The separate tiny-edge cleanup used a maximum permitted displacement of 0.00001 coordinate units, merging only endpoints of existing short edges. Actual movement was substantially smaller, as shown above. It removed the six and four tiny triangles identified previously. No new export quantization was introduced: all retained coordinates were already representable as binary STL float32 values.

No scaling, rotation, translation, voxel remeshing, smoothing, or wholesale hole filling was used. The other nine original STLs were not changed.

## Reproducibility

Run `stl_doctor.py repair` with `--weld-tolerance 0.00001`, as documented in README.md. The script chooses patches from their actual geometry; there are no rail filenames, fixed face indices, or hard-coded wall positions in its repair logic.

17 regression tests passed. All 11 original files were scanned again, reproducing the two failures and nine mesh-integrity passes. The final saved outputs were then checked in a separate script run and with the earlier read-only validator (shared algorithm lineage; not a separate CAD kernel).

## Important scope limit

This confirms mesh integrity under the performed tests, not mechanical fit, source-CAD conformity, wall thickness for a particular printer, strength, or successful slicing/printing. Verify the mating channels and slicer preview before committing to a long print.

## SHA-256 hashes

### nuts-v2-40hp-double.stl

Original: `1e1d470c9d46d1a75d72463e2a9d5c9c93dfa2426f160579e6b5e8c375c62afb`

Fixed: `d5d30f918a8c4bb1ec81665aca90763a0fce1ec5d98e6168c872df373436afd1`

### nuts-v2-60hp-double.stl

Original: `7ee057fcb437906613a3ca3e09344050c0e32d33d1a3365ddeff6bc00fc8eb84`

Fixed: `7a3c80939d1f347449ec8392fd186582b6f306f2e024d09b70dbac9607a1513f`

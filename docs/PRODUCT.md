# Product specification

## Goal

Make **zudo-stl-fix** feel like a small file utility, not CAD software:

**Drop STL files → automatic check and conservative repair → Save Fixed Files.**

All mesh processing stays on the user's Mac. No account, network upload, setup wizard, command-line use, or user-installed Python is part of the shipping experience. Nothing changes in the original files or their directories merely because they were dropped.

## Main window

One resizable native window; suggested initial size around 700 × 500. Use system typography, standard controls, system light/dark appearance, accessible status text, and restrained animation. Avoid a dashboard of advanced settings.

Text layout, not a rendered or implemented UI:

```text
zudo-stl-fix

               Drop STL files here
              or [ Choose Files… ]

rail-40hp.stl       Repair ready · 62 → 0 invalid pairs   [Details]
rail-60hp.stl       Checking…                            [Cancel]
bar.stl            No repair needed                     [Details]
other.stl          Cannot repair safely                 [Details]

Local processing · Original files stay unchanged
[Clear Finished]                         [Save Fixed Files…]
```

No 3D preview is required for v1. Do not delay the core workflow for previews, an elaborate icon, marketing pages, document editing, or a custom visual theme.

## Input and processing

Accept one or multiple local files dropped from Finder or selected through a standard multi-file open panel. Support case-insensitive `.stl` names and both binary and ASCII STL content. Validate actual content; an extension is not proof of a valid STL. Names may contain spaces, non-ASCII characters, quotes, or leading hyphens.

For v1, reject folders, archives, remote URLs, and non-STL files with an inline explanation; do not silently recurse or download. Adding valid files should still work in a mixed drop. Handle duplicate file identities without creating duplicate simultaneous jobs. Distinct files with the same basename remain distinct jobs.

Snapshot each accepted file into a private per-job working directory, record its hash and source identity, and work on that snapshot. Maintain a sequential queue by default. New drops can join while a job runs. Removing/canceling a job must not affect other completed work. Use real phase text and an indeterminate spinner where a useful percentage is unavailable; do not fabricate progress.

Start check-and-repair automatically after dropping files. Safe repair uses zero weld tolerance. Process failure, cancellation, or refusal produces no exportable repaired artifact.

## Status model

| User-facing state | Meaning |
|---|---|
| Queued / Checking / Repairing / Verifying | Work is in progress; result is not final |
| No repair needed | Completed validation found no supported repair to perform |
| Checked — review needed | No supported automatic change; a meaningful limitation/warning remains |
| Repair ready | A serialized repair passed validation and its staged bytes were verified; not yet saved by the user |
| Saved | The user-selected destination contains the verified output |
| Cannot repair safely | The mesh has a defect the engine cannot resolve conservatively |
| Check incomplete | Size, face/pair limit, timeout, or another interrupted validation |
| Error / Canceled | Operational failure or explicit cancellation |

Warnings are additional badges/messages, not hidden behind a green status. Multiple shells are not automatically a defect, but this engine does not certify their containment/orientation or repair them. A below-zero Z bound is a placement warning, not permission to translate or trim geometry.

The two supplied defective rail models should become **Repair ready with warnings** in default mode: intersections are removed but tiny-triangle warnings remain. This is an honest supported result, not a failed repair.

## Saving

Use a single **Save Fixed Files…** action to choose an output folder and save ready results. Also allow a per-row save. Choosing a destination is deliberate; no destination permission is needed before analysis. One failed file must not prevent saving other verified results.

Default name: `<original-stem>-fixed.stl`. Resolve clashes with deterministic suffixes such as `-fixed-2.stl`, including names that collide on case-insensitive filesystems. Never overwrite originals, other queue inputs, aliases/hard links to inputs, or an existing destination. Claim names exclusively at commit time; checking existence first is not enough.

Only a complete verified candidate is eligible for save. Stage and atomically publish each output in the selected destination filesystem using a no-replace mechanism. Check the final file's hash against the approved candidate. On failure, do not mark Saved, do not leave a misleading final `.stl`, and do not delete preexisting user files. Partial success in a batch is allowed and must be listed accurately. Provide **Reveal in Finder** for saved results and an optional report export. Healthy files do not produce redundant copies.

## Details and advanced control

Details disclose before/after triangle counts, invalid triangle-pair counts, bounds/dimensions, warnings, repair operations, vertex displacement/quantization, engine version, and error reasons in readable language. Detailed JSON reports remain exportable.

Advanced control: **Merge tiny existing edges**, OFF by default. Its tolerance is labeled **STL coordinate units**, with 0.00001 as an optional starting value, not a universal recommendation. Reject nonfinite, negative, or nonsensical values. Changing it affects newly started or explicitly retried jobs, not previously approved candidates. This is not a generic nearest-vertex welding feature.

STL units are unspecified. Do not label dimensions "mm" without an explicit user assumption, and never rescale just to satisfy a display label. No automatic print-bed placement. Always preserve the distinction between mesh validation and mechanical/printing suitability.

## Explicit non-goals

Generalized hole filling, free-form self-intersection reconstruction, nested-shell repair, voxel remeshing, smoothing, decimation, CAD editing, slicer integration, supports, print-bed layout, OBJ/3MF support, automatic updates, App Store submission, cloud processing, and cross-platform GUI support are outside v1.

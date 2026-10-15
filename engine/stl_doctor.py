#!/usr/bin/env python3
"""Validate STL meshes and conservatively repair folded, exactly planar patches.

Python 3.10+. Dependencies: numpy, scipy, trimesh, shapely >= 2.1.
Run `python stl_doctor.py --help` or see README.md.

No voxel remeshing, smoothing, scaling, automatic hole filling, or source overwrite.
This is a diagnostic/repair utility, not a certified CAD or printability kernel.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction as Q
import glob
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
import time
from typing import Any

try:
    import numpy as np
    import scipy
    import trimesh
    import shapely
    from shapely.geometry import Polygon
except ImportError as exc:
    raise SystemExit("Missing dependency. Run: python -m pip install -r requirements.txt\n" + str(exc))

VERSION = "1.0.0"
DTYPE = np.dtype([("normal", "<f4", (3,)), ("verts", "<f4", (3, 3)), ("attr", "<u2")])


class ResourceLimit(ValueError):
    """A bounded scan/parser could not finish; never a clean audit."""


class UnsafeRepair(ValueError):
    """The requested repair cannot be validated without guessing geometry."""


@dataclass
class STL:
    mesh: Any
    normals: Any
    raw: bytes
    format: str


def index_triangles(triangles: Any) -> Any:
    triangles = np.asarray(triangles, dtype=np.float64)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3) or not len(triangles):
        raise ValueError("STL must contain at least one triangle")
    if not np.isfinite(triangles).all():
        raise ValueError("Non-finite (NaN/infinite) vertex coordinate; not silently removed")
    vertices, inverse = np.unique(triangles.reshape(-1, 3), axis=0, return_inverse=True)
    return trimesh.Trimesh(vertices, inverse.reshape(-1, 3), process=False)


def load_stl_bytes(raw: bytes, max_faces: int | None = None) -> STL:
    """Strict binary or line-oriented ASCII parser; no tolerance-based welding."""
    if len(raw) >= 84:
        count = struct.unpack_from("<I", raw, 80)[0]
        if len(raw) == 84 + 50 * count:
            if max_faces is not None and count > max_faces:
                raise ResourceLimit("Binary STL exceeds the face limit")
            data = np.frombuffer(raw, DTYPE, count=count, offset=84)
            return STL(index_triangles(data["verts"]), data["normal"].astype(float), raw, "binary STL")
    # An ASCII STL is parsed explicitly rather than asking a loader to repair it.
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Malformed binary STL: facet count/file length mismatch, or not ASCII") from exc
    lines = [line.split() for line in text.splitlines() if line.strip()]
    i = 0
    triangles, normals = [], []
    solid_open = False
    while i < len(lines):
        tokens = lines[i]
        key = tokens[0].lower()
        if key == "solid":
            if solid_open:
                raise ValueError("Nested ASCII solid declaration")
            solid_open = True
            i += 1
        elif key == "endsolid":
            if not solid_open:
                raise ValueError("Unexpected ASCII endsolid")
            solid_open = False
            i += 1
        elif key == "facet" and solid_open:
            if len(tokens) != 5 or tokens[1].lower() != "normal" or i + 6 >= len(lines):
                raise ValueError("Malformed ASCII facet")
            if [s.lower() for s in lines[i+1]] != ["outer", "loop"]:
                raise ValueError("Missing ASCII outer loop")
            normal = [float(x) for x in tokens[2:]]
            tri = []
            for row in lines[i+2:i+5]:
                if len(row) != 4 or row[0].lower() != "vertex":
                    raise ValueError("ASCII facet must have exactly three vertices")
                tri.append([float(x) for x in row[1:]])
            if [s.lower() for s in lines[i+5]] != ["endloop"] or [s.lower() for s in lines[i+6]] != ["endfacet"]:
                raise ValueError("Missing ASCII endloop/endfacet")
            if max_faces is not None and len(triangles) >= max_faces:
                raise ResourceLimit("ASCII STL exceeds the face limit")
            triangles.append(tri)
            normals.append(normal)
            i += 7
        else:
            raise ValueError("Unexpected ASCII STL content near: " + " ".join(tokens)[:100])
    if solid_open:
        raise ValueError("Missing ASCII endsolid")
    return STL(index_triangles(triangles), np.asarray(normals, dtype=float), raw, "ASCII STL (parsed binary64)")


def load_stl(path: Path) -> STL:
    return load_stl_bytes(path.read_bytes())


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def orient2(a, b, p):
    return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])


class ExactMesh:
    """Integer lattice representing the parsed floating-point coordinates exactly."""
    def __init__(self, mesh):
        ratios = [[float(x).as_integer_ratio() for x in p] for p in mesh.vertices]
        self.scale = max(d for row in ratios for _, d in row)
        self.v = [tuple(n*(self.scale//d) for n, d in row) for row in ratios]
        self.f = [tuple(map(int, f)) for f in mesh.faces]
        self.t = [tuple(self.v[i] for i in f) for f in self.f]
        self.n = [cross(sub(t[1], t[0]), sub(t[2], t[0])) for t in self.t]
        self.c = [dot(t[0], n) for t, n in zip(self.t, self.n)]

    def plane_key(self, i):
        n, c = self.n[i], self.c[i]
        g = math.gcd(*n)
        if not g:
            return None
        if next(x for x in n if x) < 0:
            g = -g
        return tuple(x//g for x in n) + (c//g,)

    def volume6(self):
        return sum(dot(t[0], cross(t[1], t[2])) for t in self.t)


def clip2(a, b):
    out = list(a)
    direction = 1 if orient2(*b) > 0 else -1
    for k in range(3):
        p, q = b[k], b[(k+1) % 3]
        if not out:
            break
        inp, out = out, []
        previous = inp[-1]
        dp = direction*orient2(p, q, previous)
        for current in inp:
            dc = direction*orient2(p, q, current)
            if (dc >= 0) != (dp >= 0):
                ratio = Q(dp, dp-dc)
                out.append(tuple(previous[j]+ratio*(current[j]-previous[j]) for j in range(2)))
            if dc >= 0:
                out.append(current)
            previous, dp = current, dc
    return list(dict.fromkeys(out))


def coplanar_separate(a, b):
    for poly, other in ((a, b), (b, a)):
        direction = 1 if orient2(*poly) > 0 else -1
        for i in range(3):
            p, q = poly[i], poly[(i+1) % 3]
            if all(direction*orient2(p, q, v) < 0 for v in other):
                return True
    return False


def cut_interval(t, ds, k):
    values = [Q(t[i][k]) for i in range(3) if ds[i] == 0]
    for i, j in ((0, 1), (1, 2), (2, 0)):
        if ds[i]*ds[j] < 0:
            values.append(Q(t[i][k]*ds[j]-t[j][k]*ds[i], ds[j]-ds[i]))
    return min(values), max(values)


def classify_pair(ex: ExactMesh, i: int, j: int):
    a, b, fa, fb = ex.t[i], ex.t[j], ex.f[i], ex.f[j]
    na, nb = ex.n[i], ex.n[j]
    common = set(fa).intersection(fb)
    nc = len(common)
    if nc == 3:
        return {"type": "duplicate_triangle"}
    # Degenerate faces are independent validation failures, not valid planes.
    if na == (0, 0, 0) or nb == (0, 0, 0):
        return None
    line = cross(na, nb)
    parallel = line == (0, 0, 0)
    if nc == 2 and not parallel:
        return None
    da = [dot(p, nb)-ex.c[j] for p in a]
    if min(da) > 0 or max(da) < 0:
        return None
    db = [dot(p, na)-ex.c[i] for p in b]
    if min(db) > 0 or max(db) < 0:
        return None
    if parallel:
        if any(da):
            return None
        drop = max(range(3), key=lambda k: abs(na[k]))
        axes = [k for k in range(3) if k != drop]
        pa = [tuple(p[k] for k in axes) for p in a]
        pb = [tuple(p[k] for k in axes) for p in b]
        if nc == 2:
            cv = [tuple(ex.v[k][x] for x in axes) for k in common]
            va = next(pa[k] for k in range(3) if fa[k] not in common)
            vb = next(pb[k] for k in range(3) if fb[k] not in common)
            if orient2(*cv, va)*orient2(*cv, vb) <= 0:
                return None
        elif nc == 0 and coplanar_separate(pa, pb):
            return None
        poly = clip2(pa, pb)
        if not poly:
            return None
        if nc == 1:
            p = tuple(ex.v[next(iter(common))][k] for k in axes)
            if all(x == p for x in poly):
                return None
        area2 = abs(sum(poly[k][0]*poly[(k+1) % len(poly)][1]-poly[(k+1) % len(poly)][0]*poly[k][1] for k in range(len(poly))))
        if area2:
            typ = "coplanar_shared_edge_foldback" if nc == 2 else "coplanar_overlap"
        else:
            typ = "coplanar_contact_beyond_topological_join"
        return {"type": typ, "shared_vertices": nc, "projection_axes": axes,
                "projected_overlap_area": float(Q(area2, 2*ex.scale**2))}
    if nc == 1:
        for ds in (da, db):
            nz = [d for d in ds if d]
            if len(nz) == 2 and nz[0]*nz[1] > 0:
                return None
    k = max(range(3), key=lambda k: abs(line[k]))
    amin, amax = cut_interval(a, da, k)
    bmin, bmax = cut_interval(b, db, k)
    low, high = max(amin, bmin), min(amax, bmax)
    if low > high or (nc == 1 and low == high == ex.v[next(iter(common))][k]):
        return None
    return {"type": "noncoplanar_intersection" if low < high else "nonadjacent_point_contact",
            "shared_vertices": nc, "intersection_axis": k,
            "intersection_axis_span": float((high-low)/ex.scale)}


def intersections(mesh, max_faces=20_000, max_pairs=2_000_000):
    if len(mesh.faces) > max_faces:
        raise ResourceLimit(f"Exact scan limit: {len(mesh.faces)} faces exceeds --max-faces {max_faces}; NOT certified clean")
    ex = ExactMesh(mesh)
    lo, hi = mesh.triangles.min(axis=1), mesh.triangles.max(axis=1)
    defects, candidates = [], 0
    for i in range(len(ex.f)-1):
        js = np.flatnonzero(np.all(lo[i] <= hi[i+1:], axis=1) & np.all(hi[i] >= lo[i+1:], axis=1)) + i+1
        candidates += len(js)
        if candidates > max_pairs:
            raise ResourceLimit(f"Exact scan exceeds --max-pairs {max_pairs}; NOT certified clean")
        for j in js:
            item = classify_pair(ex, i, int(j))
            if item:
                item["faces"] = [i, int(j)]
                defects.append(item)
    return {"complete": True, "candidate_pairs": candidates, "defect_pair_count": len(defects),
            "affected_face_count": len({i for d in defects for i in d["faces"]}),
            "counts_by_type": dict(Counter(d["type"] for d in defects)), "defects": defects,
            "degenerate_faces_excluded_from_pair_test": sum(n == (0, 0, 0) for n in ex.n)}, ex


def topology(mesh):
    edges = defaultdict(list)
    links = [defaultdict(list) for _ in mesh.vertices]
    face_graph = [[] for _ in mesh.faces]
    for i, f in enumerate(mesh.faces):
        a, b, c = map(int, f)
        for x, y in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((x, y)))].append((i, x, y))
        for p, x, y in ((a, b, c), (b, c, a), (c, a, b)):
            links[p][x].append(y)
            links[p][y].append(x)
    winding_bad = 0
    for es in edges.values():
        if len(es) == 2 and es[0][1:] != es[1][1:][::-1]:
            winding_bad += 1
        # Star connections also handle nonmanifold edges without quadratic expansion.
        for x in es[1:]:
            face_graph[es[0][0]].append(x[0])
            face_graph[x[0]].append(es[0][0])
    bad_links = []
    for vid, graph in enumerate(links):
        if not graph:
            continue  # unreferenced vertices have no surface topology
        if any(len(v) != 2 for v in graph.values()):
            bad_links.append(vid)
            continue
        seen, stack = set(), [next(iter(graph))]
        while stack:
            p = stack.pop()
            if p not in seen:
                seen.add(p)
                stack.extend(graph[p])
        if len(seen) != len(graph):
            bad_links.append(vid)
    remaining = set(range(len(mesh.faces)))
    components = 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            for n in face_graph[stack.pop()]:
                if n in remaining:
                    remaining.remove(n)
                    stack.append(n)
    return {"boundary_edges": sum(len(x) == 1 for x in edges.values()),
            "nonmanifold_edges": sum(len(x) > 2 for x in edges.values()),
            "nonmanifold_vertex_count": len(bad_links), "nonmanifold_vertex_ids": bad_links,
            "inconsistent_edge_windings": winding_bad, "connected_shells": components}


def audit(stl: STL, max_faces=20_000, max_pairs=2_000_000):
    start = time.monotonic()
    mesh = stl.mesh
    inter, ex = intersections(mesh, max_faces, max_pairs)
    topo = topology(mesh)
    triangles = mesh.triangles
    cp = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    lengths = np.linalg.norm(cp, axis=1)
    edge_lengths = np.linalg.norm(triangles[:, [1, 2, 0]]-triangles, axis=2)
    altitude = np.divide(lengths, edge_lengths.max(axis=1), out=np.zeros(len(cp)), where=edge_lengths.max(axis=1)>0)
    areas = lengths/2
    if not np.isfinite(areas).all() or not math.isfinite(float(mesh.volume)):
        raise ValueError("Coordinate range exceeds reliable floating-point metric computation")
    duplicate = sum(c-1 for c in Counter(tuple(sorted(f)) for f in ex.f).values())
    zero = sum(n == (0, 0, 0) for n in ex.n)
    normals = np.asarray(stl.normals)
    nlen = np.linalg.norm(normals, axis=1)
    good_normals = np.isfinite(normals).all(axis=1) & (nlen > 0)
    actual = np.divide(cp, lengths[:, None], out=np.zeros_like(cp), where=lengths[:, None]>0)
    provided = np.divide(normals, nlen[:, None], out=np.zeros_like(normals), where=np.isfinite(nlen[:, None]) & (nlen[:, None]>0))
    dots = np.sum(actual*provided, axis=1)
    mismatch = int(np.sum(good_normals & (lengths > 0) & (dots < math.cos(math.radians(1)))))
    failures, warnings = [], []
    for key in ("boundary_edges", "nonmanifold_edges", "nonmanifold_vertex_count", "inconsistent_edge_windings"):
        if topo[key]:
            failures.append(key)
    if duplicate:
        failures.append("duplicate_triangles")
    if zero:
        failures.append("zero_area_triangles")
    if inter["defect_pair_count"]:
        failures.append("surface_intersections_or_invalid_contacts")
    if ex.volume6() <= 0:
        failures.append("nonpositive_total_signed_volume")
    skinny = int(np.sum(altitude < 1e-5))
    if skinny:
        warnings.append(f"{skinny} triangles have altitude < 1e-5 coordinate units (not a wall thickness measurement)")
    if mesh.bounds[0, 2] < 0:
        warnings.append("Geometry extends below Z=0; placement unchanged")
    if topo["connected_shells"] != 1:
        warnings.append("Multiple shells: containment/cavity orientation is not certified; automatic repair is refused")
    if not good_normals.all() or mismatch:
        warnings.append("Stored facet normals are missing/invalid/inconsistent; they will be regenerated on export")
    result = {"status": "FAIL" if failures else ("PASS_WITH_WARNINGS" if warnings else "PASS"),
              "failures": failures, "warnings": warnings, "sha256": hashlib.sha256(stl.raw).hexdigest() if stl.raw else None,
              "format": stl.format, "triangles": len(mesh.faces), "vertices": len(mesh.vertices),
              "bounds": mesh.bounds.tolist(), "dimensions_xyz": mesh.extents.tolist(),
              "signed_volume": float(mesh.volume), "surface_area": float(areas.sum()),
              "watertight": not topo["boundary_edges"] and not topo["nonmanifold_edges"],
              "winding_consistent": not topo["inconsistent_edge_windings"], **topo,
              "duplicate_triangles": duplicate, "zero_area_triangles": zero,
              "minimum_triangle_altitude": float(altitude.min()), "sliver_triangles_below_1e_5": skinny,
              "invalid_stored_normals": int(np.sum(~good_normals)), "stored_normal_mismatches_gt_1deg": mismatch,
              "surface_intersections": inter, "runtime_seconds": time.monotonic()-start}
    return result


def memory_stl(mesh):
    t = mesh.triangles
    n = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0])
    length = np.linalg.norm(n, axis=1)
    n = np.divide(n, length[:, None], out=np.zeros_like(n), where=length[:, None]>0)
    return STL(mesh, n, b"", "in-memory candidate")


def clean_faces(mesh):
    ex = ExactMesh(mesh)
    seen, keep = set(), []
    degenerate = duplicate = 0
    for i, f in enumerate(ex.f):
        if ex.n[i] == (0, 0, 0):
            degenerate += 1
            continue
        key = tuple(sorted(f))
        if key in seen:
            duplicate += 1
            continue
        seen.add(key)
        keep.append(i)
    if not keep:
        raise UnsafeRepair("Cleanup would remove every triangle")
    out = trimesh.Trimesh(mesh.vertices.copy(), mesh.faces[keep].copy(), process=False)
    out.remove_unreferenced_vertices()
    return out, {"exact_zero_area_faces_removed": degenerate, "exact_duplicate_faces_removed": duplicate}


def directed_boundary(faces):
    entries = defaultdict(list)
    for f in faces:
        for a, b in zip(f, (*f[1:], f[0])):
            entries[tuple(sorted((a, b)))].append((a, b))
    result = []
    for edges in entries.values():
        if len(edges) == 1:
            result.append(edges[0])
        elif len(edges) != 2 or edges[0] != edges[1][::-1]:
            raise UnsafeRepair("Patch has nonmanifold or inconsistently directed internal edges")
    return result


def boundary_loops(boundary):
    nxt, prev = {}, {}
    for a, b in boundary:
        if a in nxt or b in prev:
            raise UnsafeRepair("Patch boundary branches or touches itself")
        nxt[a], prev[b] = b, a
    if not nxt or set(nxt) != set(prev):
        raise UnsafeRepair("Patch boundary does not form closed loops")
    unseen, loops = set(nxt), []
    while unseen:
        start = min(unseen)
        v, loop = start, []
        while v in unseen:
            unseen.remove(v)
            loop.append(v)
            v = nxt[v]
        if v != start or len(loop) < 3:
            raise UnsafeRepair("Invalid patch boundary cycle")
        loops.append(loop)
    return loops


def triangulate_patch(mesh, ex, face_ids):
    """Replace an exactly planar connected patch using its ORIGINAL oriented boundary."""
    if not hasattr(shapely, "constrained_delaunay_triangles"):
        raise UnsafeRepair("Planar repair needs shapely>=2.1 and GEOS>=3.10")
    old = [ex.f[i] for i in face_ids]
    boundary = directed_boundary(old)
    loops = boundary_loops(boundary)
    normal = ex.n[face_ids[0]]
    drop = max(range(3), key=lambda k: abs(normal[k]))
    axes = [k for k in range(3) if k != drop]
    ip = [tuple(v[k] for k in axes) for v in ex.v]
    fp = np.asarray(mesh.vertices)[:, axes]
    def loop_area2(loop):
        return sum(ip[a][0]*ip[b][1]-ip[b][0]*ip[a][1] for a, b in zip(loop, loop[1:]+loop[:1]))
    loops.sort(key=lambda loop: abs(loop_area2(loop)), reverse=True)
    signs = [loop_area2(loop) for loop in loops]
    if not signs[0] or any(s == 0 or s*signs[0] > 0 for s in signs[1:]):
        raise UnsafeRepair("Boundary is not one outer ring with oppositely oriented holes")
    outer = Polygon(fp[loops[0]])
    if not outer.is_valid or any(not outer.contains(Polygon(fp[loop])) for loop in loops[1:]):
        raise UnsafeRepair("Patch boundary is geometrically invalid or has multiple outer regions")
    polygon = Polygon(fp[loops[0]], [fp[loop] for loop in loops[1:]])
    if not polygon.is_valid or polygon.area <= 0:
        raise UnsafeRepair("Patch has intersecting/invalid boundary rings")
    wanted_area2 = sum(orient2(*(ip[k] for k in f)) for f in old)
    if wanted_area2 != sum(signs):
        raise UnsafeRepair("Original oriented area differs from its boundary")
    # New vertices are forbidden: triangulation must reuse exact existing coordinates.
    coordinate_ids = {tuple(fp[i]): i for loop in loops for i in loop}
    if len(coordinate_ids) != sum(len(loop) for loop in loops):
        raise UnsafeRepair("Projected boundary has duplicate coordinates")
    new = []
    for tri in shapely.constrained_delaunay_triangles(polygon).geoms:
        coords = list(tri.exterior.coords)[:-1]
        if len(coords) != 3:
            raise UnsafeRepair("Triangulator did not return triangles")
        try:
            f = [coordinate_ids[tuple(p)] for p in coords]
        except KeyError as exc:
            raise UnsafeRepair("Triangulator inserted/moved a boundary vertex") from exc
        a = orient2(*(ip[k] for k in f))
        if not a:
            raise UnsafeRepair("Triangulator created a degenerate triangle")
        if a*signs[0] < 0:
            f.reverse()
        new.append(tuple(f))
    if Counter(directed_boundary(new)) != Counter(boundary):
        raise UnsafeRepair("Triangulation did not preserve every directed boundary segment")
    if sum(orient2(*(ip[k] for k in f)) for f in new) != wanted_area2:
        raise UnsafeRepair("Retriangulation changed exact oriented patch area")
    volume_old = sum(dot(ex.v[f[0]], cross(ex.v[f[1]], ex.v[f[2]])) for f in old)
    volume_new = sum(dot(ex.v[f[0]], cross(ex.v[f[1]], ex.v[f[2]])) for f in new)
    if volume_old != volume_new:
        raise UnsafeRepair("Retriangulation changed exact algebraic volume")
    return new, {"method": "exact-plane boundary-preserving constrained triangulation",
                 "face_ids_at_patch_stage": sorted(face_ids), "faces_removed": len(old), "faces_added": len(new),
                 "boundary_vertices_preserved": len(coordinate_ids), "boundary_segments_preserved": len(boundary),
                 "plane_key_integer_lattice": list(ex.plane_key(face_ids[0])), "projection_axes": axes,
                 "patch_bounds_before": [mesh.triangles[face_ids].min(axis=(0, 1)).tolist(), mesh.triangles[face_ids].max(axis=(0, 1)).tolist()],
                 "exact_signed_area_preserved": True, "exact_signed_volume_preserved": True,
                 "new_vertex_coordinates_introduced": 0}


def repair_planar(mesh, scan, ex):
    seed = set()
    for d in scan["defects"]:
        if d["type"] in ("coplanar_overlap", "coplanar_shared_edge_foldback"):
            seed.update(d["faces"])
    if not seed:
        return mesh.copy(), [], []
    groups = defaultdict(list)
    for i in range(len(ex.f)):
        key = ex.plane_key(i)
        if key is not None:
            groups[key].append(i)
    chosen_keys = {ex.plane_key(i) for i in seed}
    replacements, removed, reports, rejected = [], set(), [], []
    for key in sorted(chosen_keys):
        ids = groups[key]
        edges = defaultdict(list)
        graph = defaultdict(set)
        for i in ids:
            f = ex.f[i]
            for a, b in zip(f, (*f[1:], f[0])):
                edges[tuple(sorted((a, b)))].append(i)
        for es in edges.values():
            for i in es[1:]:
                graph[es[0]].add(i)
                graph[i].add(es[0])
        remaining = set(ids)
        while remaining:
            first = min(remaining)
            remaining.remove(first)
            component, stack = {first}, [first]
            while stack:
                for i in graph[stack.pop()]:
                    if i in remaining:
                        remaining.remove(i)
                        component.add(i)
                        stack.append(i)
            if not component.intersection(seed):
                continue
            try:
                new, report = triangulate_patch(mesh, ex, sorted(component))
            except UnsafeRepair as exc:
                rejected.append({"face_ids_at_patch_stage": sorted(component), "reason": str(exc)})
                continue
            removed.update(component)
            replacements.extend(new)
            reports.append(report)
    if not removed:
        return mesh.copy(), reports, rejected
    keep = [f for i, f in enumerate(ex.f) if i not in removed]
    out = trimesh.Trimesh(mesh.vertices.copy(), np.asarray(keep+replacements, dtype=np.int64), process=False)
    out.remove_unreferenced_vertices()
    return out, reports, rejected


def collapse_tiny_edges(mesh, tolerance):
    """Opt-in only: merge short EXISTING edges, not arbitrary close opposing walls."""
    if tolerance <= 0:
        return mesh.copy(), {"tolerance": 0.0, "vertices_merged": 0, "maximum_vertex_displacement": 0.0}
    # Only existing edges are eligible. Enumerating every nearby vertex pair
    # first can allocate quadratic memory even though nonedges are discarded.
    adjacent = np.asarray(mesh.edges_unique)
    lengths = np.linalg.norm(mesh.vertices[adjacent[:, 0]]-mesh.vertices[adjacent[:, 1]], axis=1)
    pairs = sorted(tuple(sorted(map(int, edge))) for edge in adjacent[lengths <= tolerance])
    parent = list(range(len(mesh.vertices)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in pairs:
        a, b = root(a), root(b)
        parent[max(a, b)] = min(a, b)
    groups = defaultdict(list)
    for i in range(len(parent)):
        groups[root(i)].append(i)
    mapped = np.arange(len(parent))
    skipped = 0
    for rep, members in groups.items():
        if max(np.linalg.norm(mesh.vertices[members]-mesh.vertices[rep], axis=1)) > tolerance:
            skipped += 1  # prevent transitive chains from exceeding the requested tolerance
            continue
        mapped[members] = rep
    displacement = np.linalg.norm(mesh.vertices-mesh.vertices[mapped], axis=1)
    out = trimesh.Trimesh(mesh.vertices.copy(), mapped[mesh.faces], process=False)
    out, cleanup = clean_faces(out)
    return out, {"tolerance": tolerance, "vertices_merged": int(np.sum(mapped != np.arange(len(mapped)))),
                 "maximum_vertex_displacement": float(displacement.max()), "over_tolerance_clusters_skipped": skipped,
                 "existing_mesh_edges_only": True, **cleanup}


def export_binary(mesh):
    """Regenerate normals from the actual float32 output coordinates."""
    original = np.asarray(mesh.vertices)
    with np.errstate(over="ignore", invalid="ignore"):
        quantized = original.astype("<f4").astype(np.float64)
    if not np.isfinite(quantized).all():
        raise UnsafeRepair("Coordinates exceed binary STL float32 range")
    t = quantized[mesh.faces]
    n = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0])
    length = np.linalg.norm(n, axis=1)
    if np.any(length == 0):
        raise UnsafeRepair("Binary STL serialization would create zero-area triangles")
    data = np.zeros(len(t), dtype=DTYPE)
    data["verts"] = t
    data["normal"] = n/length[:, None]
    header = (f"stl_doctor {VERSION}; verified planar repair; STL units unchanged").encode("ascii").ljust(80, b" ")[:80]
    raw = header + struct.pack("<I", len(t)) + data.tobytes()
    return raw, float(np.linalg.norm(quantized-original, axis=1).max())


def repair(stl, before, weld_tolerance=0.0, max_faces=20_000, max_pairs=2_000_000):
    original = stl.mesh
    if before["connected_shells"] != 1:
        raise UnsafeRepair("Automatic repair supports a single shell only; separate/nested parts need review")
    mesh, cleanup = clean_faces(original)
    topo = topology(mesh)
    if topo["boundary_edges"] or topo["nonmanifold_edges"] or topo["nonmanifold_vertex_count"]:
        raise UnsafeRepair("Open/nonmanifold mesh after exact cleanup; no automatic hole filling or guessed reconstruction")
    if topo["connected_shells"] != 1:
        raise UnsafeRepair("Cleanup changed the number of shells")
    old_faces = mesh.faces.copy()
    # One closed shell only: do not turn cavity shells into positive-volume solids.
    trimesh.repair.fix_normals(mesh, multibody=False)
    flipped = int(np.sum(np.any(mesh.faces != old_faces, axis=1)))
    reference_volume = float(mesh.volume)
    scan, ex = intersections(mesh, max_faces, max_pairs)
    mesh, patches, refused_patches = repair_planar(mesh, scan, ex)
    mesh, weld = collapse_tiny_edges(mesh, weld_tolerance)
    raw, quantization = export_binary(mesh)
    reread = load_stl_bytes(raw)
    after = audit(reread, max_faces, max_pairs)
    if after["failures"]:
        raise UnsafeRepair("Exported candidate failed revalidation: " + ", ".join(after["failures"]))
    if after["connected_shells"] != 1:
        raise UnsafeRepair("Candidate changed the number of connected shells")
    bounds_change = float(np.max(np.abs(original.bounds-reread.mesh.bounds)))
    if bounds_change > weld_tolerance+quantization+1e-12:
        raise UnsafeRepair("Candidate moved the bounds beyond the allowed vertex displacement")
    volume_change = float(reread.mesh.volume-reference_volume)
    relative_volume_change = abs(volume_change)/max(abs(reference_volume), np.finfo(float).tiny)
    if relative_volume_change > 1e-6:
        raise UnsafeRepair("Candidate changed algebraic volume by more than the 1e-6 relative guard")
    report = {"cleanup": cleanup, "faces_reoriented": flipped, "planar_patches": patches,
              "refused_planar_patches": refused_patches, "tiny_edge_cleanup": weld,
              "binary_export_maximum_vertex_quantization": quantization,
              "maximum_bounds_coordinate_change": bounds_change,
              "signed_volume_change_from_oriented_cleaned_input": volume_change,
              "relative_signed_volume_change": relative_volume_change,
              "geometry_rescaled_rotated_or_translated": False,
              "validation_performed_after_binary_serialization": True,
              "note": "Patch face IDs refer to the cleaned/oriented pre-patch mesh, not necessarily the raw file."}
    return raw, after, report


def write_safe(path: Path, content: bytes, overwrite: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb" if overwrite else "xb") as f:
        f.write(content)


def expand_inputs(values):
    paths = []
    for value in values:
        matches = sorted(glob.glob(value)) if glob.has_magic(value) else [value]
        if not matches:
            raise ValueError(f"No files match: {value}")
        for match in matches:
            path = Path(match)
            if path.is_dir():
                found = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".stl")
                if not found:
                    raise ValueError(f"No STL files in directory: {path}")
                paths.extend(found)
            else:
                paths.append(path)
    result, seen = [], set()
    for p in paths:
        p = p.resolve()
        if p not in seen:
            result.append(p)
            seen.add(p)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("check", "repair"))
    parser.add_argument("files", nargs="+", help="STL paths, quoted globs, or directories (non-recursive)")
    parser.add_argument("--out-dir", type=Path, default=Path("repaired"))
    parser.add_argument("--report", type=Path, default=Path("stl-report.json"))
    parser.add_argument("--weld-tolerance", type=float, default=0.0,
                        help="Opt-in collapse of existing short edges, in STL units. Default 0 (no approximate welding).")
    parser.add_argument("--max-faces", type=int, default=20_000)
    parser.add_argument("--max-pairs", type=int, default=2_000_000)
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing destination files/report; NEVER an input STL")
    args = parser.parse_args(argv)
    if not math.isfinite(args.weld_tolerance) or args.weld_tolerance < 0 or args.max_faces < 1 or args.max_pairs < 1:
        parser.error("Tolerances must be finite and nonnegative; scan limits must be positive")
    if args.mode == "check" and args.weld_tolerance:
        parser.error("--weld-tolerance is a repair option")
    try:
        inputs = expand_inputs(args.files)
        report_path = args.report.resolve()
        if report_path.suffix.lower() != ".json" or report_path in inputs:
            raise ValueError("--report must be a .json file different from every input")
        if report_path.exists() and not args.overwrite:
            raise FileExistsError(f"Report exists: {report_path}; choose a new path or use --overwrite")
        destinations = [args.out_dir.resolve()/(p.stem+"-fixed.stl") for p in inputs]
        if any(p in inputs for p in destinations):
            raise ValueError("Output would overwrite an input STL; choose a different --out-dir")
        if len(set(destinations)) != len(destinations):
            raise ValueError("Input files have duplicate basenames; run them into separate output directories")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    records, errors, failures = [], False, False
    for path, dest in zip(inputs, destinations):
        item = {"input": str(path), "output": None}
        try:
            stl = load_stl(path)
            before = audit(stl, args.max_faces, args.max_pairs)
            item["before"] = before
            if args.mode == "check":
                item["action"] = "checked"
                failures |= bool(before["failures"])
                print(f"{before['status']:18s} {path.name}: {before['surface_intersections']['defect_pair_count']} invalid triangle pairs", flush=True)
            else:
                needs_work = bool(before["failures"] or before["invalid_stored_normals"] or before["stored_normal_mismatches_gt_1deg"]
                                  or (args.weld_tolerance > 0 and before["sliver_triangles_below_1e_5"]))
                if not needs_work:
                    item["action"] = "unchanged"
                    item["after"] = before
                    print(f"UNCHANGED          {path.name}", flush=True)
                else:
                    if dest.exists() and not args.overwrite:
                        raise FileExistsError(f"Output exists: {dest}; choose a new directory or use --overwrite")
                    raw, after, details = repair(stl, before, args.weld_tolerance, args.max_faces, args.max_pairs)
                    # Ensure the original did not change while we worked.
                    if hashlib.sha256(path.read_bytes()).hexdigest() != before["sha256"]:
                        raise UnsafeRepair("Input changed during processing; no output written")
                    write_safe(dest, raw, args.overwrite)
                    # Also verify the bytes actually written to disk.
                    if dest.read_bytes() != raw:
                        raise OSError("Written output differs from validated bytes")
                    item.update(action="repaired", output=str(dest), after=after, repair_details=details)
                    print(f"REPAIRED / {after['status']:8s} {path.name} -> {dest}", flush=True)
        except UnsafeRepair as exc:
            item.update(action="refused", error=str(exc))
            failures = True
            print(f"REFUSED            {path.name}: {exc}", file=sys.stderr, flush=True)
        except Exception as exc:
            item.update(action="error", error=f"{type(exc).__name__}: {exc}")
            errors = True
            print(f"ERROR              {path.name}: {exc}", file=sys.stderr, flush=True)
        records.append(item)
    report = {"tool": "stl_doctor", "version": VERSION, "mode": args.mode, "units": "STL coordinate units; no unit conversion",
              "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                              "trimesh": trimesh.__version__, "shapely": shapely.__version__, "GEOS": shapely.geos_version_string},
              "scope": "Exact intersection predicates on parsed coordinates; floating-point geometric metrics; conservative single-shell planar repair.",
              "limitations": ["No certification of wall thickness, hardware fit, strength, source-CAD intent or slicing.",
                              "No generalized noncoplanar reconstruction, automatic hole filling, voxelization, smoothing, or nested-shell orientation repair.",
                              "ASCII decimal values are first parsed as binary64. Binary STL is checked on its exact stored float32 coordinates.",
                              "Worst-case quadratic broad phase; explicit resource limits fail closed, never report an incomplete scan as clean."],
              "files": records}
    try:
        write_safe(report_path, (json.dumps(report, indent=2, allow_nan=False)+"\n").encode(), args.overwrite)
    except Exception as exc:
        print(f"ERROR writing report: {exc}", file=sys.stderr)
        return 2
    print(f"Report: {report_path}", flush=True)
    return 2 if errors else (1 if failures else 0)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""One bounded v1 NDJSON job; final user destinations belong to the native app."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import stat
import struct
import sys
import uuid

import stl_doctor as d

PROTOCOL_VERSION = 1
MAX_REQUEST = 16 * 1024
MAX_INPUT = 64 * 1024 * 1024
MAX_REPORT = 16 * 1024 * 1024
MAX_LINE = 256 * 1024
MAX_FACES = 20_000
MAX_PAIRS = 2_000_000


class WorkerError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encode(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def environment():
    return {"python": platform.python_version(), "architecture": platform.machine(),
            "numpy": d.np.__version__, "scipy": d.scipy.__version__,
            "trimesh": d.trimesh.__version__, "shapely": d.shapely.__version__,
            "GEOS": d.shapely.geos_version_string, "engine": d.VERSION}


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise WorkerError("protocol_error", "Duplicate JSON member")
        obj[key] = value
    return obj


def bad_constant(_):
    raise WorkerError("protocol_error", "Nonfinite JSON number")


def read_request(stream):
    raw = stream.read(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST:
        raise WorkerError("protocol_error", "Request exceeds 16 KiB")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=bad_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WorkerError("protocol_error", "Request must be one bounded UTF-8 JSON object") from exc
    if not isinstance(value, dict):
        raise WorkerError("protocol_error", "Request must be an object")
    return value


def validate_request(req):
    required = {"protocol_version", "job_id", "operation", "input_path", "staging_directory", "options"}
    if set(req) != required or type(req["protocol_version"]) is not int or req["protocol_version"] != 1:
        raise WorkerError("protocol_error", "Unsupported protocol version or request fields")
    try:
        if not isinstance(req["job_id"], str) or str(uuid.UUID(req["job_id"])) != req["job_id"].lower():
            raise ValueError()
    except (ValueError, AttributeError):
        raise WorkerError("protocol_error", "job_id must be a UUID") from None
    if req["operation"] != "check_and_repair":
        raise WorkerError("protocol_error", "Unsupported operation")
    options = req["options"]
    if not isinstance(options, dict) or set(options) != {"weld_tolerance", "max_faces", "max_pairs"}:
        raise WorkerError("protocol_error", "Unexpected options")
    tolerance = options["weld_tolerance"]
    if type(tolerance) not in (int, float) or not 0 <= tolerance <= 1 or not math.isfinite(tolerance):
        raise WorkerError("invalid_input", "Tolerance must be finite and between 0 and 1 STL coordinate units")
    for name, cap in (("max_faces", MAX_FACES), ("max_pairs", MAX_PAIRS)):
        if type(options[name]) is not int or not 1 <= options[name] <= cap:
            raise WorkerError("invalid_input", f"{name} must be a positive integer no greater than {cap}")
    for name in ("input_path", "staging_directory"):
        value = req[name]
        if not isinstance(value, str) or not value or "\0" in value:
            raise WorkerError("invalid_input", "Invalid job path")
        path = Path(value)
        if not path.is_absolute() or ".." in path.parts or str(path) != value:
            raise WorkerError("invalid_input", "Job paths must be normalized absolute paths")
    root, source = Path(req["staging_directory"]), Path(req["input_path"])
    if source.parent != root or source.suffix.lower() != ".stl":
        raise WorkerError("invalid_input", "Snapshot must be an STL directly inside its job directory")
    if source.name in {"candidate.stl", "report.json"}:
        raise WorkerError("invalid_input", "Snapshot name collides with worker artifacts")
    return root, source.name, options


class JobFiles:
    """Pin the private directory descriptor; never follow final-component links."""
    def __init__(self, root):
        if root.resolve(strict=True) != root:
            raise WorkerError("invalid_input", "Job directory must not use symbolic links")
        self.root = root
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.created = {}
        self.identities = {}

    def close(self):
        os.close(self.fd)

    def read(self, name, cap):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            initial = os.fstat(fd)
            if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
                raise WorkerError("invalid_input", "Job artifacts must be regular files with one hard link")
            if initial.st_size > cap:
                raise d.ResourceLimit("File exceeds the byte limit")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(cap + 1)
            final = os.fstat(fd)
            current = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(initial) != identity(final) or identity(final) != identity(current):
                raise WorkerError("input_changed", "Job file changed while reading")
            if name in self.identities and self.identities[name] != identity(current):
                raise WorkerError("input_changed", "Job file identity changed during processing")
            self.identities[name] = identity(current)
            if len(raw) > cap:
                raise d.ResourceLimit("File exceeds the byte limit")
            return raw
        finally:
            os.close(fd)

    def write(self, name, raw, cap):
        if len(raw) > cap:
            raise d.ResourceLimit("Artifact exceeds the byte limit")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.created[name] = os.fstat(fd).st_ino
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        if self.read(name, cap) != raw:
            raise WorkerError("verification_failed", "Stored artifact differs from approved bytes")
        return {"relative_path": name, "sha256": digest(raw), "byte_size": len(raw)}

    def check_snapshot(self, name, original):
        if digest(self.read(name, MAX_INPUT)) != digest(original):
            raise WorkerError("input_changed", "Snapshot changed during processing")
        pinned, named = os.fstat(self.fd), os.stat(self.root, follow_symlinks=False)
        if (pinned.st_dev, pinned.st_ino) != (named.st_dev, named.st_ino):
            raise WorkerError("input_changed", "Job directory changed during processing")

    def cleanup(self):
        for name, inode in self.created.items():
            try:
                if os.stat(name, dir_fd=self.fd, follow_symlinks=False).st_ino == inode:
                    os.unlink(name, dir_fd=self.fd)
            except FileNotFoundError:
                pass


def preflight(raw, max_faces):
    """Bound parser allocation before it creates arrays or a tokenized line list."""
    if len(raw) >= 84 and len(raw) == 84 + 50 * struct.unpack_from("<I", raw, 80)[0]:
        if struct.unpack_from("<I", raw, 80)[0] > max_faces:
            raise d.ResourceLimit("Binary STL exceeds the face limit")
        return
    facets, lines = 0, 0
    for line in io.BytesIO(raw):
        lines += 1
        if len(line) > 4096 or lines > max_faces * 10 + 1024:
            raise d.ResourceLimit("ASCII STL exceeds bounded parser limits")
        if line.lstrip().lower().startswith(b"facet "):
            facets += 1
            if facets > max_faces:
                raise d.ResourceLimit("ASCII STL exceeds the face limit")


def compact(audit):
    if audit is None:
        return None
    result = {k: v for k, v in audit.items() if k not in {"surface_intersections", "nonmanifold_vertex_ids"}}
    result["surface_intersections"] = {k: v for k, v in audit["surface_intersections"].items() if k != "defects"}
    return result


def compact_details(details):
    if details is None:
        return None
    return {**{k: v for k, v in details.items() if k not in {"planar_patches", "refused_planar_patches"}},
            "planar_patches_repaired": len(details.get("planar_patches", [])),
            "planar_patches_refused": len(details.get("refused_planar_patches", []))}


def warnings(audit):
    if audit is None:
        return []
    codes = []
    if audit["sliver_triangles_below_1e_5"]:
        codes.append("tiny_triangles")
    if audit["bounds"][0][2] < 0:
        codes.append("below_zero_z")
    if audit["connected_shells"] != 1:
        codes.append("multiple_shells")
    if audit["invalid_stored_normals"] or audit["stored_normal_mismatches_gt_1deg"]:
        codes.append("stored_normals")
    return [{"code": code, "message": message} for code, message in zip(codes, audit["warnings"], strict=True)]


def run(req, emit):
    root, source, options = validate_request(req)
    files = None
    before = after = details = original = None
    candidate = report = None
    outcome, status, error = "error", None, None
    exit_code = 1
    emit("started")
    try:
        files = JobFiles(root)
        emit("progress", phase="checking", message="Checking snapshot and exact triangle intersections")
        original = files.read(source, MAX_INPUT)
        preflight(original, options["max_faces"])
        stl = d.load_stl_bytes(original, max_faces=options["max_faces"])
        before = d.audit(stl, options["max_faces"], options["max_pairs"])
        if before["surface_intersections"]["complete"] is not True:
            raise d.ResourceLimit("Intersection scan did not finish")
        needs_work = bool(before["failures"] or before["invalid_stored_normals"] or
                          before["stored_normal_mismatches_gt_1deg"] or
                          (options["weld_tolerance"] > 0 and before["sliver_triangles_below_1e_5"]))
        if not needs_work:
            after, outcome = before, "unchanged"
        else:
            emit("progress", phase="repairing", message="Attempting conservative single-shell repair")
            raw, after, details = d.repair(stl, before, **options)
            emit("progress", phase="verifying", message="Revalidating serialized coordinates and staged bytes")
            # Independently audit the actual returned bytes, not only engine metadata.
            after = d.audit(d.load_stl_bytes(raw, max_faces=options["max_faces"]), options["max_faces"], options["max_pairs"])
            if after["surface_intersections"]["complete"] is not True or after["failures"]:
                raise WorkerError("verification_failed", "Serialized repair did not pass a complete audit")
            candidate = files.write("candidate.stl", raw, MAX_INPUT)
            outcome = "repaired"
        status, exit_code = after["status"], 0
    except d.UnsafeRepair as exc:
        outcome, error, exit_code = "refused", {"code": "unsupported_geometry", "message": str(exc)}, 0
        status = before["status"] if before else None
    except d.ResourceLimit as exc:
        outcome, error, exit_code = "incomplete", {"code": "resource_limit", "message": str(exc)}, 0
    except WorkerError as exc:
        error = {"code": exc.code, "message": str(exc)}
    except PermissionError:
        error = {"code": "permission_denied", "message": "Permission denied accessing private job files"}
    except (ValueError, OverflowError) as exc:
        error = {"code": "invalid_input", "message": str(exc)[:1024]}
    except OSError as exc:
        error = {"code": "verification_failed" if before else "invalid_input",
                 "message": f"Private job file I/O failed (errno {exc.errno})"}
    except Exception as exc:
        error = {"code": "worker_crashed", "message": f"Unexpected worker failure: {type(exc).__name__}"}
    try:
        if files:
            if original is not None:
                files.check_snapshot(source, original)
            if outcome not in {"repaired", "unchanged", "refused"}:
                files.cleanup()
                candidate = None
            full = {"protocol_version": 1, "job_id": req["job_id"], "environment": environment(),
                    "outcome": outcome, "options": options, "before": before, "after": after,
                    "repair_details": details, "error": error,
                    "limitations": ["Mesh validation is not proof of printability, fit, strength or design intent.",
                                    "STL coordinate units are unspecified; no scaling or placement changes.",
                                    "Only conservative single-shell repair is supported."]}
            report = files.write("report.json", encode(full), MAX_REPORT)
        result = {"outcome": outcome, "validation_status": status,
                  "summary": {"before": compact(before), "after": compact(after),
                              "repair_details": compact_details(details), "engine_version": d.VERSION,
                              "input_sha256": digest(original) if original is not None else None, "options": options},
                  "warnings": warnings(after or before), "candidate": candidate, "report": report, "error": error}
        # All encoding/bounds checks precede the terminal event. Never emit success then an error.
        if len(encode({"protocol_version": 1, "job_id": req["job_id"], "event": "result", **result})) > MAX_LINE:
            raise d.ResourceLimit("Result exceeds protocol line limit")
        emit("result", **result)
        return exit_code
    except Exception:
        if files:
            files.cleanup()
        raise
    finally:
        if files:
            files.close()


def self_test():
    """Exercise imported binary dependencies and a real folded planar repair."""
    polygon = d.Polygon([(0, 0), (3, 0), (3, 3), (0, 3)], holes=[[(1, 1), (1, 2), (2, 2), (2, 1)]])
    triangles = d.shapely.constrained_delaunay_triangles(polygon)
    if abs(sum(t.area for t in triangles.geoms) - polygon.area) > 1e-12:
        raise RuntimeError("Constrained triangulation failed")
    points = d.np.array([[x, y, z] for x, ys in [(-1., (-2., 2.)), (1., (-1., 1.))] for y in ys for z in (-1., 1.)])
    mesh = d.trimesh.convex.convex_hull(points)  # SciPy native convex hull
    ids = d.np.flatnonzero(d.np.all(mesh.triangles[:, :, 0] == 1, axis=1))
    boundary = d.directed_boundary([tuple(map(int, mesh.faces[i])) for i in ids])
    vertices = d.np.vstack([mesh.vertices, [1, 1.5, 0]])
    faces = [tuple(map(int, f)) for i, f in enumerate(mesh.faces) if i not in ids]
    faces += [(a, b, len(vertices)-1) for a, b in boundary]
    stl = d.memory_stl(d.trimesh.Trimesh(vertices, faces, process=False))
    before = d.audit(stl)
    raw, after, details = d.repair(stl, before)
    if not before["failures"] or after["failures"] or not details["planar_patches"] or not raw:
        raise RuntimeError("Synthetic repair failed")
    return {"protocol_version": 1, "self_test": "passed", "environment": environment()}


def main():
    if sys.argv[1:] == ["--self-test"]:
        sys.stdout.buffer.write(encode(self_test()))
        return 0
    job_id = "00000000-0000-0000-0000-000000000000"
    def emit(event, **fields):
        raw = encode({"protocol_version": 1, "job_id": job_id, "event": event, **fields})
        if len(raw) > MAX_LINE:
            raise d.ResourceLimit("Protocol line exceeds limit")
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
    try:
        if sys.argv[1:]:
            raise WorkerError("protocol_error", "Unexpected command line arguments")
        req = read_request(sys.stdin.buffer)
        validate_request(req)
        job_id = req["job_id"]
        return run(req, emit)
    except Exception as exc:
        code = exc.code if isinstance(exc, WorkerError) else "worker_crashed"
        if isinstance(exc, d.ResourceLimit):
            code = "resource_limit"
        if isinstance(exc, PermissionError):
            code = "permission_denied"
        try:
            emit("result", outcome="incomplete" if isinstance(exc, d.ResourceLimit) else "error",
                 validation_status=None, summary={}, warnings=[], candidate=None,
                 report=None, error={"code": code, "message": str(exc)[:1024]})
        except (OSError, ValueError):
            pass
        return 0 if isinstance(exc, d.ResourceLimit) else 1


if __name__ == "__main__":
    raise SystemExit(main())

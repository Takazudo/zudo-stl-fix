#!/usr/bin/env python3
"""Verify supplied assets and optionally re-run geometry checks and repairs.

Run from anywhere. Python 3.10+. --hashes-only needs no third-party packages.
This is a development verifier, not the app worker or a production export path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(f.read()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fixture_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    require(path.is_relative_to(ROOT / 'fixtures'), 'Fixture path leaves fixtures directory')
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hashes-only', action='store_true', help='Check all 13 reference file hashes without geometry dependencies')
    parser.add_argument('--repair', action='store_true', help='Also reproduce both repairs, with welding disabled and with tolerance 1e-5')
    parser.add_argument('--report', type=Path, help='Write a new JSON report; never overwrite an existing report')
    args = parser.parse_args()
    if args.hashes_only and args.repair:
        parser.error('--hashes-only cannot be combined with --repair')
    if args.report and args.report.exists():
        parser.error('Report already exists; select a new path')
    manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
    records: list[dict[str, Any]] = []
    start = time.monotonic()
    engine = None
    environment: dict[str, Any] = {'python': platform.python_version(), 'platform': platform.platform()}
    if not args.hashes_only:
        sys.path.insert(0, str(ROOT / 'engine'))
        import stl_doctor as engine
        environment.update({name: getattr(engine, name).__version__ for name in ('np', 'scipy', 'trimesh', 'shapely')})
        environment['GEOS'] = engine.shapely.geos_version_string
    for entry in manifest['files']:
        record: dict[str, Any] = {'path': entry['path'], 'kind': 'hash' if args.hashes_only else 'audit'}
        try:
            path = fixture_path(entry['path'])
            require(digest(path) == entry['sha256'], 'Reference SHA-256 does not match manifest')
            require(path.stat().st_size == entry['size_bytes'], 'Reference file size changed')
            if engine is not None:
                result = engine.audit(engine.load_stl(path))
                for field, expected in entry['expected'].items():
                    require(result[field] == expected, f'{field}: {result[field]!r} != {expected!r}')
                require(result['surface_intersections']['defect_pair_count'] == entry['expected_invalid_triangle_pairs'], 'Intersection pair count changed')
                record.update(mesh_status=result['status'], triangles=result['triangles'], invalid_pairs=result['surface_intersections']['defect_pair_count'])
            record['passed'] = True
        except Exception as exc:
            record.update(passed=False, error=f'{type(exc).__name__}: {exc}')
        records.append(record)
        print(('PASS' if record['passed'] else 'FAIL') + ' ' + entry['path'], flush=True)
    if args.repair:
        for case in manifest['repair_cases']:
            for tolerance in (0.0, case['weld_tolerance']):
                record = {'path': case['input'], 'kind': 'repair', 'weld_tolerance': tolerance}
                try:
                    path = fixture_path(case['input'])
                    original_hash = digest(path)
                    stl = engine.load_stl(path)
                    before = engine.audit(stl)
                    raw, after, details = engine.repair(stl, before, weld_tolerance=tolerance)
                    # Reopen a real temporary file, not just the in-memory mesh.
                    with tempfile.TemporaryDirectory(prefix='zudo-stl-fix-fixture-') as temp:
                        candidate = Path(temp) / 'candidate.stl'
                        candidate.write_bytes(raw)
                        reread = engine.audit(engine.load_stl(candidate))
                    require(not reread['failures'], 'Serialized repair failed validation')
                    require(reread['surface_intersections']['defect_pair_count'] == 0, 'Repair retained invalid surface pairs')
                    require(reread['connected_shells'] == 1, 'Repair changed shell count')
                    require(reread['bounds'] == before['bounds'], 'Reference case bounding box changed')
                    require(details['maximum_bounds_coordinate_change'] == 0, 'Reference case bounds guard changed')
                    require(digest(path) == original_hash, 'Original file was modified')
                    if tolerance:
                        require(reread['triangles'] == case['expected_triangle_count'], 'Triangle count differs from cleaned reference')
                        require(reread['sliver_triangles_below_1e_5'] == 0, 'Opt-in cleanup retained reference sliver triangles')
                        require(details['tiny_edge_cleanup']['maximum_vertex_displacement'] <= tolerance, 'Welding exceeded tolerance')
                    else:
                        require(details['tiny_edge_cleanup']['vertices_merged'] == 0, 'Default mode welded vertices')
                        require(details['binary_export_maximum_vertex_quantization'] == 0, 'Binary reference coordinates changed on serialization')
                        require(reread['sliver_triangles_below_1e_5'] == before['sliver_triangles_below_1e_5'], 'Default mode unexpectedly removed tiny-triangle warnings')
                    record.update(passed=True, mesh_status=reread['status'], triangles=reread['triangles'], invalid_pairs=0, warnings=reread['warnings'], bounds_changed=False, candidate_sha256=hashlib.sha256(raw).hexdigest())
                except Exception as exc:
                    record.update(passed=False, error=f'{type(exc).__name__}: {exc}')
                records.append(record)
                print(('PASS' if record['passed'] else 'FAIL') + f" repair {case['input']} weld={tolerance:g}", flush=True)
    failed = sum(not r['passed'] for r in records)
    result = {'project': 'zudo-stl-fix', 'scope': 'Development asset and baseline-engine verification; not a macOS app test', 'environment': environment, 'runtime_seconds': time.monotonic()-start, 'checks': len(records), 'failed': failed, 'results': records}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x', encoding='utf-8') as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write('\n')
    print(f"{len(records)-failed}/{len(records)} checks passed")
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())

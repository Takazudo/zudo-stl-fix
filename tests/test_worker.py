"""Worker boundaries, actual geometry outcomes, and immutable staged bytes."""
import hashlib
import errno
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import stl_doctor as d
import worker as w


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.input = self.root / "日本 語 'box.STL"
        self.raw, _ = d.export_binary(d.trimesh.creation.box())
        self.input.write_bytes(self.raw)
        self.req = {"protocol_version": 1, "job_id": str(uuid.uuid4()), "operation": "check_and_repair",
                    "input_path": str(self.input), "staging_directory": str(self.root),
                    "options": {"weld_tolerance": 0., "max_faces": 20_000, "max_pairs": 2_000_000}}

    def execute(self, req=None):
        events = []
        code = w.run(req or self.req, lambda event, **fields: events.append({"event": event, **fields}))
        self.assertEqual(events[0]["event"], "started")
        self.assertEqual(sum(e["event"] == "result" for e in events), 1)
        self.assertEqual(events[-1]["event"], "result")
        return code, events[-1]

    def process(self, raw):
        result = subprocess.run([sys.executable, str(ROOT / "engine/worker.py")], input=raw,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(events)
        self.assertTrue(all(len(line) <= w.MAX_LINE for line in result.stdout.splitlines()))
        self.assertEqual(events[-1]["event"], "result")
        return result.returncode, events[-1]

    def assert_artifact(self, descriptor):
        raw = (self.root / descriptor["relative_path"]).read_bytes()
        self.assertEqual(len(raw), descriptor["byte_size"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), descriptor["sha256"])
        return raw

    def test_healthy_binary_no_candidate_and_warning_visible(self):
        code, result = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(result["outcome"], "unchanged")
        self.assertIsNone(result["candidate"])
        self.assertIn("below_zero_z", [x["code"] for x in result["warnings"]])
        self.assertTrue(result["summary"]["after"]["surface_intersections"]["complete"])
        self.assert_artifact(result["report"])
        self.assertEqual(self.input.read_bytes(), self.raw)

    def test_ascii_and_protocol_subprocess(self):
        self.input.write_text(d.trimesh.creation.box().export(file_type="stl_ascii"))
        code, result = self.process(w.encode(self.req))
        self.assertEqual(code, 0)
        self.assertEqual(result["outcome"], "unchanged")
        self.assertEqual(result["job_id"], self.req["job_id"])

    def test_strict_json(self):
        cases = [b'{"a":1,"a":2}', b'[]', b'{}{}', b'NaN', b'{"v":Infinity}', b'\xff',
                 b'x' * (w.MAX_REQUEST + 1), b'[' * 2000 + b']' * 2000]
        for raw in cases:
            with self.subTest(raw=raw[:30]), self.assertRaises(w.WorkerError):
                w.read_request(io.BytesIO(raw))

    def test_invalid_protocol_process(self):
        code, result = self.process(b'{"protocol_version":1,"protocol_version":2}')
        self.assertNotEqual(code, 0)
        self.assertEqual(result["error"]["code"], "protocol_error")
        self.assertIsNone(result["candidate"])

    def test_request_validation(self):
        for key, values in {"protocol_version": [True, 2, 1.0], "job_id": ["x", 3],
                            "operation": ["check", None], "input_path": ["relative.stl", "\0", str(self.root / '../x.stl')]}.items():
            for value in values:
                req = {**self.req, key: value}
                with self.subTest(key=key, value=value), self.assertRaises(w.WorkerError):
                    w.validate_request(req)
        for key, values in {"weld_tolerance": [-1, float('nan'), float('inf'), True, 2],
                            "max_faces": [True, 0, 20_001, 12.5], "max_pairs": [0, 2_000_001, "4"]}.items():
            for value in values:
                req = {**self.req, "options": {**self.req["options"], key: value}}
                with self.subTest(key=key, value=value), self.assertRaises(w.WorkerError):
                    w.validate_request(req)
        with self.assertRaises(w.WorkerError):
            w.validate_request({**self.req, "extra": 1})

    def test_input_extension_and_containment(self):
        for name in [str(self.root / 'sub/input.stl'), str(self.root / 'input.obj'), str(self.root / 'candidate.stl')]:
            with self.subTest(name=name), self.assertRaises(w.WorkerError):
                w.validate_request({**self.req, 'input_path': name})

    def test_invalid_stl_and_nonfinite_vertices(self):
        for content in [b'not STL', self.raw[:-1], self.raw[:96] + struct.pack('<f', float('nan')) + self.raw[100:]]:
            self.input.write_bytes(content)
            code, result = self.execute()
            self.assertNotEqual(code, 0)
            self.assertEqual(result['error']['code'], 'invalid_input')
            self.assertIsNone(result['candidate'])
            (self.root / 'report.json').unlink()

    def test_face_limit_binary_before_allocation(self):
        self.req['options']['max_faces'] = 1
        with mock.patch.object(d, 'index_triangles', side_effect=AssertionError('must not allocate')):
            code, result = self.execute()
        self.assertEqual((code, result['outcome']), (0, 'incomplete'))
        self.assertEqual(result['error']['code'], 'resource_limit')
        self.assertIsNone(result['validation_status'])

    def test_ascii_face_limit(self):
        self.req['options']['max_faces'] = 1
        self.input.write_text(d.trimesh.creation.box().export(file_type='stl_ascii'))
        code, result = self.execute()
        self.assertEqual((code, result['outcome']), (0, 'incomplete'))

    def test_pair_limit_incomplete_not_success(self):
        self.req['options']['max_pairs'] = 1
        code, result = self.execute()
        self.assertEqual((code, result['outcome']), (0, 'incomplete'))
        self.assertIsNone(result['candidate'])
        self.assertIsNone(result['validation_status'])

    def test_byte_limit_precedes_read(self):
        with mock.patch.object(w, 'MAX_INPUT', 32):
            code, result = self.execute()
        self.assertEqual((code, result['outcome']), (0, 'incomplete'))

    def test_ascii_line_bounds(self):
        for raw in [b'solid ' + b'a' * 4096, b'\n' * 1035]:
            with self.assertRaises(d.ResourceLimit):
                w.preflight(raw, 1)

    def test_unsupported_open_mesh_refused_without_candidate(self):
        mesh = d.trimesh.creation.box()
        mesh.update_faces(list(range(len(mesh.faces)-1)))
        self.input.write_bytes(d.export_binary(mesh)[0])
        code, result = self.execute()
        self.assertEqual((code, result['outcome']), (0, 'refused'))
        self.assertEqual(result['error']['code'], 'unsupported_geometry')
        self.assertIsNone(result['candidate'])
        self.assertFalse((self.root / 'candidate.stl').exists())

    def test_symlink_snapshot_rejected(self):
        other = self.root / 'actual.stl'
        self.input.rename(other)
        self.input.symlink_to(other)
        code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertIsNone(result['candidate'])

    def test_hardlink_snapshot_rejected(self):
        os.link(self.input, self.root / 'alias.stl')
        code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'invalid_input')

    def test_fifo_rejected_without_hang(self):
        self.input.unlink()
        os.mkfifo(self.input)
        code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'invalid_input')

    def test_unchanged_snapshot_change_detected(self):
        original = d.audit
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            self.input.write_bytes(b'changed')
            return result
        with mock.patch.object(d, 'audit', side_effect=changed), self.assertRaises(w.WorkerError) as error:
            self.execute()
        self.assertEqual(error.exception.code, 'input_changed')
        self.assertFalse((self.root / 'candidate.stl').exists())

    def inverted(self):
        box = d.trimesh.creation.box()
        box.invert()
        self.input.write_bytes(d.export_binary(box)[0])

    def test_actual_serialized_candidate_is_reaudited(self):
        self.inverted()
        before = d.audit(d.load_stl_bytes(self.raw))
        with mock.patch.object(d, 'repair', return_value=(self.input.read_bytes(), before, {})):
            code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'verification_failed')
        self.assertIsNone(result['candidate'])

    def test_report_collision_preserves_existing_and_cleans_candidate(self):
        self.inverted()
        report = self.root / 'report.json'
        report.write_bytes(b'user data')
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(report.read_bytes(), b'user data')
        self.assertFalse((self.root / 'candidate.stl').exists())

    def test_candidate_collision_preserves_existing(self):
        self.inverted()
        path = self.root / 'candidate.stl'
        path.write_bytes(b'existing')
        code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertEqual(path.read_bytes(), b'existing')
        self.assertIsNone(result['candidate'])

    def test_corrupt_write_cleans_candidate(self):
        self.inverted()
        original = w.JobFiles.read
        def corrupt(files, name, cap):
            raw = original(files, name, cap)
            return b'corrupt' if name == 'candidate.stl' else raw
        with mock.patch.object(w.JobFiles, 'read', corrupt):
            code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'verification_failed')
        self.assertFalse((self.root / 'candidate.stl').exists())

    def test_disk_failure_removes_partial_artifact(self):
        self.inverted()
        real_fsync = os.fsync
        failed = False
        def full_disk(fd):
            nonlocal failed
            if not failed:
                failed = True
                raise OSError(errno.ENOSPC, 'No space left on device')
            return real_fsync(fd)
        with mock.patch.object(os, 'fsync', side_effect=full_disk):
            code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'verification_failed')
        self.assertIsNone(result['candidate'])
        self.assertFalse((self.root / 'candidate.stl').exists())

    def test_terminated_worker_never_returns_success(self):
        manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
        self.input.write_bytes((ROOT / manifest['repair_cases'][0]['input']).read_bytes())
        process = subprocess.Popen([sys.executable, str(ROOT / 'engine/worker.py')], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.stdin.write(w.encode(self.req))
            process.stdin.close()
            first = json.loads(process.stdout.readline())
            self.assertEqual(first['event'], 'started')
            process.terminate()
            process.wait(timeout=10)
            self.assertNotEqual(process.returncode, 0)
            events = [json.loads(line) for line in process.stdout.read().splitlines()]
            self.assertFalse(any(e['event'] == 'result' and e.get('outcome') in {'repaired', 'unchanged'} for e in events))
            self.assertFalse((self.root / 'candidate.stl').exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()

    def test_terminal_failure_cleans_artifacts(self):
        self.inverted()
        def emit(event, **fields):
            if event == 'result':
                raise BrokenPipeError()
        with self.assertRaises(BrokenPipeError):
            w.run(self.req, emit)
        self.assertFalse((self.root / 'candidate.stl').exists())
        self.assertFalse((self.root / 'report.json').exists())

    def test_report_bound_cleans_candidate(self):
        self.inverted()
        with mock.patch.object(w, 'MAX_REPORT', 10), self.assertRaises(d.ResourceLimit):
            self.execute()
        self.assertFalse((self.root / 'candidate.stl').exists())

    def test_false_scan_completion_rejected(self):
        original = d.audit
        def incomplete(*args, **kwargs):
            result = original(*args, **kwargs)
            result['surface_intersections']['complete'] = False
            return result
        with mock.patch.object(d, 'audit', side_effect=incomplete):
            code, result = self.execute()
        self.assertEqual((code, result['outcome']), (0, 'incomplete'))
        self.assertIsNone(result['candidate'])

    def test_self_test_dependencies(self):
        result = subprocess.run([sys.executable, str(ROOT / 'engine/worker.py'), '--self-test'],
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['self_test'], 'passed')

    def test_permission_failure_is_structured(self):
        with mock.patch.object(w, 'JobFiles', side_effect=PermissionError()):
            code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'permission_denied')
        self.assertIsNone(result['candidate'])

    def test_unexpected_engine_failure_is_structured(self):
        with mock.patch.object(d, 'audit', side_effect=RuntimeError('unexpected')):
            code, result = self.execute()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'worker_crashed')
        self.assertIsNone(result['candidate'])

    def test_all_nine_healthy_originals_unchanged(self):
        manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
        files = [entry for entry in manifest['files']
                 if entry['kind'] == 'original' and not entry['expected_invalid_triangle_pairs']]
        self.assertEqual(len(files), 9)
        for entry in files:
            with self.subTest(input=entry['path']):
                original = (ROOT / entry['path']).read_bytes()
                self.input.write_bytes(original)
                code, result = self.execute()
                self.assertEqual((code, result['outcome']), (0, 'unchanged'))
                self.assertIsNone(result['candidate'])
                self.assertEqual(self.input.read_bytes(), original)
                self.assertEqual(result['summary']['after']['sha256'], entry['sha256'])
                (self.root / 'report.json').unlink()

    def test_both_real_rail_repairs_default_and_opt_in(self):
        manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
        for case in manifest['repair_cases']:
            for tolerance in [0., 1e-5]:
                with self.subTest(input=case['input'], tolerance=tolerance):
                    raw = (ROOT / case['input']).read_bytes()
                    self.input.write_bytes(raw)
                    self.req['options']['weld_tolerance'] = tolerance
                    code, result = self.execute()
                    self.assertEqual((code, result['outcome']), (0, 'repaired'))
                    before, after = result['summary']['before'], result['summary']['after']
                    self.assertEqual(before['surface_intersections']['defect_pair_count'], 62)
                    self.assertEqual(after['surface_intersections']['defect_pair_count'], 0)
                    self.assertEqual(before['bounds'], after['bounds'])
                    self.assertEqual(after['connected_shells'], 1)
                    self.assertFalse(after['failures'])
                    if tolerance == 0:
                        self.assertIn('tiny_triangles', [x['code'] for x in result['warnings']])
                    else:
                        self.assertEqual(after['triangles'], case['expected_triangle_count'])
                        self.assertEqual(after['sliver_triangles_below_1e_5'], 0)
                    candidate = self.assert_artifact(result['candidate'])
                    self.assertEqual(after['sha256'], w.digest(candidate))
                    self.assert_artifact(result['report'])
                    self.assertEqual(self.input.read_bytes(), raw)
                    (self.root / 'candidate.stl').unlink()
                    (self.root / 'report.json').unlink()


class ExistingEdgeBoundsTests(unittest.TestCase):
    def mesh(self, coordinates, edges):
        # Isolate edge eligibility from topology repair. The clean_faces step is
        # mocked so deliberately open synthetic geometry can reveal the mapping.
        class EdgeMesh:
            vertices = d.np.asarray(coordinates, dtype=float)
            edges_unique = d.np.asarray(edges)
            faces = d.np.array([[0, 1, 2], [0, 2, 3]])
            def copy(self):
                return self
        return EdgeMesh()

    def collapse(self, mesh, tolerance):
        with mock.patch.object(d, 'clean_faces', side_effect=lambda m: (m, {})):
            return d.collapse_tiny_edges(mesh, tolerance)[1]

    def test_nonadjacent_close_vertices_do_not_merge(self):
        mesh = self.mesh([[0, 0, 0], [1e-6, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 2], [1, 3]])
        self.assertEqual(self.collapse(mesh, 1e-5)['vertices_merged'], 0)

    def test_zero_and_exact_tolerance(self):
        mesh = self.mesh([[0, 0, 0], [0.125, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1]])
        self.assertEqual(self.collapse(mesh, 0)['vertices_merged'], 0)
        self.assertEqual(self.collapse(mesh, 0.124)['vertices_merged'], 0)
        self.assertEqual(self.collapse(mesh, 0.125)['vertices_merged'], 1)

    def test_transitive_cluster_cannot_exceed_displacement(self):
        mesh = self.mesh([[0, 0, 0], [0.125, 0, 0], [0.25, 0, 0], [0, 1, 0]], [[0, 1], [1, 2]])
        details = self.collapse(mesh, 0.125)
        self.assertEqual(details['vertices_merged'], 0)
        self.assertEqual(details['over_tolerance_clusters_skipped'], 1)


if __name__ == '__main__':
    unittest.main()

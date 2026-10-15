"""Regression tests. Run: python -m unittest -v test_stl_doctor.py"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon
import shapely
import stl_doctor as d


def as_stl(mesh):
    return d.memory_stl(mesh)


def folded_frustum():
    points = np.array([[x, y, z] for x, ys in [(-1.0, (-2.0, 2.0)), (1.0, (-1.0, 1.0))] for y in ys for z in (-1.0, 1.0)])
    mesh = trimesh.convex.convex_hull(points)
    ids = np.flatnonzero(np.all(mesh.triangles[:, :, 0] == 1, axis=1))
    boundary = d.directed_boundary([tuple(map(int, mesh.faces[i])) for i in ids])
    vertices = np.vstack([mesh.vertices, [1, 1.5, 0]])
    p = len(vertices)-1
    faces = [tuple(map(int, f)) for i, f in enumerate(mesh.faces) if i not in ids]
    faces += [(a, b, p) for a, b in boundary]
    return trimesh.Trimesh(vertices, faces, process=False)


class STLDoctorTests(unittest.TestCase):
    def setUp(self):
        self.box = trimesh.creation.box()

    def fix(self, mesh, **kwargs):
        stl = as_stl(mesh)
        return d.repair(stl, d.audit(stl), **kwargs)

    def test_clean_box(self):
        result = d.audit(as_stl(self.box))
        self.assertFalse(result['failures'])
        self.assertEqual(result['surface_intersections']['defect_pair_count'], 0)

    def test_planar_fold_detected_and_repaired(self):
        mesh = folded_frustum()
        before = d.audit(as_stl(mesh))
        self.assertGreater(before['surface_intersections']['defect_pair_count'], 0)
        raw, after, details = self.fix(mesh)
        self.assertFalse(after['failures'])
        self.assertEqual(after['surface_intersections']['defect_pair_count'], 0)
        self.assertEqual(len(details['planar_patches']), 1)
        self.assertEqual(details['maximum_bounds_coordinate_change'], 0)
        self.assertAlmostEqual(mesh.volume, d.load_stl_bytes(raw).mesh.volume)

    def test_non_axis_aligned_planar_fold(self):
        mesh = folded_frustum()
        # Exactly representable shear: x' = x + z. The patch is now x'-z=1.
        mesh.vertices = np.asarray(mesh.vertices) @ np.array([[1, 0, 0], [0, 1, 0], [1, 0, 1]])
        _, after, details = self.fix(mesh)
        self.assertFalse(after['failures'])
        self.assertEqual(len(details['planar_patches']), 1)
        self.assertEqual(details['maximum_bounds_coordinate_change'], 0)

    def test_inverted_shell_reoriented(self):
        self.box.invert()
        self.assertIn('nonpositive_total_signed_volume', d.audit(as_stl(self.box))['failures'])
        _, after, details = self.fix(self.box)
        self.assertFalse(after['failures'])
        self.assertGreater(details['faces_reoriented'], 0)

    def test_duplicate_and_zero_area_faces(self):
        faces = np.vstack([self.box.faces, self.box.faces[0], [0, 0, 1]])
        mesh = trimesh.Trimesh(self.box.vertices, faces, process=False)
        before = d.audit(as_stl(mesh))
        self.assertEqual(before['duplicate_triangles'], 1)
        self.assertEqual(before['zero_area_triangles'], 1)
        _, after, details = self.fix(mesh)
        self.assertFalse(after['failures'])
        self.assertEqual(details['cleanup']['exact_duplicate_faces_removed'], 1)
        self.assertEqual(details['cleanup']['exact_zero_area_faces_removed'], 1)

    def test_open_mesh_refused(self):
        mesh = trimesh.Trimesh(self.box.vertices, self.box.faces[:-1], process=False)
        self.assertGreater(d.audit(as_stl(mesh))['boundary_edges'], 0)
        with self.assertRaises(d.UnsafeRepair):
            self.fix(mesh)

    def test_crossing_multiple_shells_refused(self):
        other = self.box.copy()
        other.apply_translation([0.3, 0.2, 0.1])
        mesh = trimesh.util.concatenate([self.box, other])
        before = d.audit(as_stl(mesh))
        self.assertGreater(before['surface_intersections']['defect_pair_count'], 0)
        with self.assertRaises(d.UnsafeRepair):
            self.fix(mesh)

    def test_nonplanar_single_shell_intersection_refused(self):
        mesh = folded_frustum()
        mesh.vertices[-1, 0] = 0.875
        before = d.audit(as_stl(mesh))
        self.assertEqual(before['connected_shells'], 1)
        self.assertGreater(before['surface_intersections']['counts_by_type'].get('noncoplanar_intersection', 0), 0)
        with self.assertRaises(d.UnsafeRepair):
            self.fix(mesh)

    def test_nonmanifold_point_contact(self):
        other = self.box.copy()
        other.apply_translation([1, 1, 1])
        mesh = d.index_triangles(np.vstack([self.box.triangles, other.triangles]))
        before = d.audit(as_stl(mesh))
        self.assertGreater(before['nonmanifold_vertex_count'], 0)
        with self.assertRaises(d.UnsafeRepair):
            self.fix(mesh)

    def test_optional_short_edge_cleanup(self):
        a, b = map(int, self.box.edges_unique[0])
        vertices = np.vstack([self.box.vertices, self.box.vertices[a] + (self.box.vertices[b]-self.box.vertices[a])*2**-20])
        p = len(vertices)-1
        faces = []
        for original in self.box.faces:
            f = list(map(int, original))
            if a in f and b in f:
                for k in range(3):
                    u, v, w = f[k], f[(k+1)%3], f[(k+2)%3]
                    if {u, v} == {a, b}:
                        faces += [(u, p, w), (p, v, w)]
                        break
            else:
                faces.append(f)
        mesh = trimesh.Trimesh(vertices, faces, process=False)
        before = d.audit(as_stl(mesh))
        self.assertFalse(before['failures'])
        self.assertGreater(before['sliver_triangles_below_1e_5'], 0)
        _, unchanged, details0 = self.fix(mesh)
        self.assertEqual(details0['tiny_edge_cleanup']['vertices_merged'], 0)
        self.assertGreater(unchanged['sliver_triangles_below_1e_5'], 0)
        _, after, details = self.fix(mesh, weld_tolerance=1e-5)
        self.assertFalse(after['failures'])
        self.assertEqual(after['sliver_triangles_below_1e_5'], 0)
        self.assertLessEqual(details['tiny_edge_cleanup']['maximum_vertex_displacement'], 1e-5)

    def test_hole_boundary_preserved_by_patch_triangulation(self):
        poly = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)], holes=[[(1, 1), (1, 3), (3, 3), (3, 1)]])
        ts = []
        for triangle in shapely.constrained_delaunay_triangles(poly).geoms:
            xy = np.array(triangle.exterior.coords)[:3]
            if d.orient2(*xy) < 0:
                xy = xy[::-1]
            ts.append(np.column_stack([xy, np.zeros(3)]))
        mesh = d.index_triangles(ts)
        ex = d.ExactMesh(mesh)
        new, details = d.triangulate_patch(mesh, ex, list(range(len(mesh.faces))))
        self.assertEqual(len(d.boundary_loops(d.directed_boundary(new))), 2)
        self.assertTrue(details['exact_signed_area_preserved'])
        self.assertEqual(details['boundary_segments_preserved'], 8)

    def test_ascii_parse(self):
        text = self.box.export(file_type='stl_ascii')
        stl = d.load_stl_bytes(text.encode())
        self.assertFalse(d.audit(stl)['failures'])
        self.assertEqual(len(stl.mesh.faces), 12)

    def test_binary_roundtrip(self):
        raw, displacement = d.export_binary(self.box)
        stl = d.load_stl_bytes(raw)
        self.assertEqual(displacement, 0)
        self.assertFalse(d.audit(stl)['failures'])

    def test_malformed_input(self):
        with self.assertRaises(ValueError):
            d.load_stl_bytes(b'not an STL')
        raw, _ = d.export_binary(self.box)
        with self.assertRaises(ValueError):
            d.load_stl_bytes(raw[:-1])
        with self.assertRaises(ValueError):
            d.load_stl_bytes(b'solid test\nfacet normal 0 0 1\nouter loop\nvertex nan 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid test\n')

    def test_resource_limit_is_not_pass(self):
        with self.assertRaises(ValueError):
            d.audit(as_stl(self.box), max_faces=1)
        with self.assertRaises(ValueError):
            d.audit(as_stl(self.box), max_pairs=1)

    def test_cli_preserves_input_and_refuses_destination_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root/'fold.stl'
            raw, _ = d.export_binary(folded_frustum())
            path.write_bytes(raw)
            args = ['repair', str(path), '--out-dir', str(root/'out'), '--report', str(root/'first.json')]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(d.main(args), 0)
                args[-1] = str(root/'second.json')
                self.assertEqual(d.main(args), 2)
            self.assertEqual(path.read_bytes(), raw)
            fixed = root/'out'/'fold-fixed.stl'
            self.assertTrue(fixed.exists())
            self.assertFalse(d.audit(d.load_stl(fixed))['failures'])

    def test_cli_refusal_does_not_write_fixed_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mesh = trimesh.Trimesh(self.box.vertices, self.box.faces[:-1], process=False)
            raw, _ = d.export_binary(mesh)
            path = root/'open.stl'
            path.write_bytes(raw)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = d.main(['repair', str(path), '--out-dir', str(root/'out'), '--report', str(root/'report.json')])
            self.assertEqual(code, 1)
            self.assertFalse((root/'out'/'open-fixed.stl').exists())
            self.assertEqual(path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()

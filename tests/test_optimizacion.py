"""Regresión de las optimizaciones de rendimiento y calidad gráfica.

Comprueba que el redibujado parcial produce exactamente lo mismo que el
completo, que los cálculos acelerados dan los mismos resultados que los
originales y que el formato de proyecto no cambia.

    python -m unittest discover -s tests -v
    (Linux sin pantalla: xvfb-run -a python -m unittest discover -s tests -v)
"""
from __future__ import annotations

import random
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import core  # noqa: E402
import quality_render  # noqa: E402
from core import (make_symbol, make_wire, make_straight_wire, junction_points,  # noqa: E402
                  point_on_segment, port_positions, save_project, load_project)


def junction_points_reference(doc):
    """Implementación original de la V0.5.3 (sin prefiltro)."""
    endpoints = {}
    for wire in doc['wires']:
        for endpoint in (tuple(wire['points'][0]), tuple(wire['points'][-1])):
            endpoints.setdefault(endpoint, set()).add(wire['id'])
    result = set()
    for point, owners in endpoints.items():
        if len(owners) >= 3:
            result.add(point)
            continue
        for wire in doc['wires']:
            if wire['id'] in owners:
                continue
            if any(point_on_segment(point, a, b, strict=True)
                   for a, b in zip(wire['points'], wire['points'][1:])):
                result.add(point)
                break
    return sorted(result)


class GeometryEquivalence(unittest.TestCase):
    def test_junction_points_same_as_original(self):
        rnd = random.Random(7)
        for _ in range(60):
            wires = []
            for _ in range(rnd.randint(2, 40)):
                a = (rnd.randrange(2, 30) * 20, rnd.randrange(2, 20) * 20)
                b = (rnd.randrange(2, 30) * 20, rnd.randrange(2, 20) * 20)
                if a == b:
                    continue
                if rnd.random() < .15:
                    wires.append(make_straight_wire(a, b))
                else:
                    wires.append(make_wire(a, b, rnd.random() < .5))
            doc = {'elements': [], 'wires': wires}
            self.assertEqual(junction_points(doc), junction_points_reference(doc))


@unittest.skipUnless(quality_render.AVAILABLE, 'Pillow no disponible')
class RenderCache(unittest.TestCase):
    def test_symbol_bitmap_independent_of_position(self):
        zoom = 1.37
        a = make_symbol('contact_no', 200, 300, 'S1', draw_scale=core.COMPACT_SCALE)
        # Desplazamiento que conserva la fracción de píxel del origen.
        b = make_symbol('contact_no', 200 + 100, 300 + 100, 'S1', draw_scale=core.COMPACT_SCALE)
        sa = core.symbol_shapes(a, include_annotations=False)
        sb = core.symbol_shapes(b, include_annotations=False)
        self.assertEqual(quality_render.shapes_key(sa, a['x'], a['y']),
                         quality_render.shapes_key(sb, b['x'], b['y']))
        ia, la, ta = quality_render.render(sa, zoom, origin=(a['x'], a['y']))
        ib, lb, tb = quality_render.render(sb, zoom, origin=(b['x'], b['y']))
        phase_a = quality_render.origin_phase(a['x'], a['y'], zoom)[2:]
        phase_b = quality_render.origin_phase(b['x'], b['y'], zoom)[2:]
        if phase_a == phase_b:
            self.assertEqual((la, ta), (lb, tb))
            self.assertEqual(ia.tobytes(), ib.tobytes())

    def test_orthogonal_lines_are_pixel_exact(self):
        # Una línea vertical de 1 px debe ocupar una sola columna opaca.
        img, left, top = quality_render.render([('line', 10, 0, 10, 40)], 1.0, width=1)
        alpha = img.getchannel('A')
        w, h = img.size
        row = [alpha.getpixel((x, h // 2)) for x in range(w)]
        self.assertEqual(sum(1 for v in row if v == 255), 1)
        self.assertEqual(sum(1 for v in row if 0 < v < 255), 0)

    def test_legacy_api_still_available(self):
        result = quality_render.symbol_bitmap([('circle', 40, 40, 5)], .65)
        self.assertIsNotNone(result)
        self.assertIsNotNone(quality_render.label_bitmap(('text', 0, 0, 'K1', 12, '#000000'), 1.0))


class ProjectFormat(unittest.TestCase):
    def test_save_load_roundtrip_unchanged(self):
        project = core.new_project('Prueba')
        doc = project['sheets'][0]
        a = make_symbol('contact_no', 200, 200, 'S1', draw_scale=doc['drawing_scale'])
        b = make_symbol('contact_nc', 200, 400, 'S2', draw_scale=doc['drawing_scale'])
        doc['elements'] = [a, b]
        doc['wires'] = [make_wire(port_positions(a)[-1], port_positions(b)[0])]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'p.ework'
            save_project(project, path)
            loaded = load_project(path)
            save_project(loaded, Path(tmp) / 'q.ework')
            self.assertEqual(path.read_text(encoding='utf-8'),
                             (Path(tmp) / 'q.ework').read_text(encoding='utf-8'))
        self.assertEqual(loaded['sheets'][0]['elements'], doc['elements'])
        self.assertEqual(loaded['sheets'][0]['wires'], doc['wires'])


class PartialRedrawGUI(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Tkinter sin pantalla disponible: {exc}')
        self.root.geometry('1400x900')
        from electrical_work import ElectricalWorkApp
        from bench_rendimiento import build_sheet
        self.app = ElectricalWorkApp(self.root)
        self.root.update()
        self.elements, self.wires = build_sheet(self.app.doc, 8, 4, 120, 160)
        self.app.redraw()
        self.root.update()

    def tearDown(self):
        if hasattr(self, 'root'):
            self.root.destroy()

    def _state(self):
        cv = self.app.canvas
        boxes = {}
        for el in self.app.doc['elements']:
            boxes['element:' + el['id']] = cv.bbox('element:' + el['id'])
        for w in self.app.doc['wires']:
            boxes['wire:' + w['id']] = cv.bbox('wire:' + w['id'])
        dots = sorted(tuple(cv.coords(i)) for i in cv.find_withtag('junction-dot'))
        return boxes, dots, len(cv.find_withtag('dyn')) >= 0

    def _widget(self, x, y):
        cv = self.app.canvas
        px, py = self.app._xy(x, y)
        return round(px - cv.canvasx(0)), round(py - cv.canvasy(0))

    def _drag_without_release(self, start, steps, step):
        cv = self.app.canvas
        x, y = self._widget(*start)
        cv.event_generate('<ButtonPress-1>', x=x, y=y)
        self.root.update()
        for i in range(1, steps + 1):
            tx, ty = self._widget(start[0] + step[0] * i, start[1] + step[1] * i)
            cv.event_generate('<B1-Motion>', x=tx, y=ty)
            self.root.update()
        return tx, ty

    def _assert_partial_equals_full(self):
        partial = self._state()
        self.app.redraw()
        self.root.update()
        full = self._state()
        self.assertEqual(partial[0], full[0])
        self.assertEqual(partial[1], full[1])

    def test_single_drag_partial_equals_full(self):
        el = self.elements[9]
        self._drag_without_release((el['x'], el['y']), 6, (10, 10))
        self.assertIsNotNone(self.app.dragging)
        self.assertTrue(self.app.dragging['changed'])
        self._assert_partial_equals_full()

    def test_group_drag_partial_equals_full(self):
        group = {('element', e['id']) for e in self.elements[:8]}
        group |= {('wire', w['id']) for w in self.wires[:6]}
        self.app.multi_selected = set(group)
        self.app.redraw()
        self.root.update()
        first = self.elements[0]
        self._drag_without_release((first['x'], first['y']), 5, (10, 0))
        self.assertEqual(self.app.dragging['mode'], 'group')
        self._assert_partial_equals_full()

    def test_drag_release_undo_restores_document(self):
        before = [dict(e) for e in self.app.doc['elements']]
        el = self.elements[5]
        tx, ty = self._drag_without_release((el['x'], el['y']), 4, (10, 0))
        self.app.canvas.event_generate('<ButtonRelease-1>', x=tx, y=ty)
        self.root.update()
        self.assertTrue(self.app.dirty)
        self.app.undo()
        self.root.update()
        self.assertEqual([(e['x'], e['y']) for e in self.app.doc['elements']],
                         [(e['x'], e['y']) for e in before])

    def test_progressive_wheel_zoom_ends_identical_to_full(self):
        cv = self.app.canvas
        for _ in range(3):
            cv.event_generate('<Button-4>', x=400, y=300)
        self.root.update()
        if quality_render.AVAILABLE:
            self.assertTrue(self.app._pending_quality or self.app._refine_job)
        # Esperar al afinado en segundo plano.
        for _ in range(400):
            self.root.update()
            if not self.app._pending_quality and self.app._refine_job is None:
                break
            self.root.after(10)
        self.assertFalse(self.app._pending_quality)
        refined = self._state()
        images = len(cv.find_withtag('drawing'))
        self.app.redraw()
        self.root.update()
        self.assertEqual(refined[0], self._state()[0])
        self.assertEqual(images, len(cv.find_withtag('drawing')))

    def test_static_layer_kept_and_rebuilt_on_zoom(self):
        cv = self.app.canvas
        static = cv.find_withtag('static')
        self.app.redraw()
        self.assertEqual(static, cv.find_withtag('static'))
        self.app.set_zoom(180)
        self.root.update()
        self.assertNotEqual(static, cv.find_withtag('static'))
        self.assertTrue(cv.find_withtag('static'))


if __name__ == '__main__':
    unittest.main()

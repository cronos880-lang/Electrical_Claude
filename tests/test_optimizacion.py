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


class WireRepair(unittest.TestCase):
    """Cables que la edición deja de longitud cero no deben impedir guardar."""

    def _cases(self):
        return [
            {'id': 'a1', 'points': [[320, 540], [320, 540], [320, 540]]},   # tras girar
            {'id': 'a2', 'points': [[740, 220], [740, 220]]},               # tras mover grupo
            {'id': 'a3', 'points': [[1030, 390], [1030, 390]], 'mode': 'straight'},
            {'id': 'a4', 'points': [[100, 100], [100, 100], [200, 100], [300, 200]]},  # duplicado + oblicuo
            {'id': 'ok', 'points': [[100, 300], [400, 300]]},
        ]

    def test_repair_allows_saving_and_keeps_valid_wires(self):
        project = core.new_project('Reparar')
        doc = project['sheets'][0]
        doc['wires'] = self._cases()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                save_project(project, Path(tmp) / 'antes.ework')
            fixed = core.repair_wires(doc)
            self.assertEqual(fixed, 4)
            save_project(project, Path(tmp) / 'despues.ework')
            loaded = load_project(Path(tmp) / 'despues.ework')
        wires = {w['id']: w['points'] for w in loaded['sheets'][0]['wires']}
        self.assertEqual(set(wires), {'a4', 'ok'})
        self.assertEqual(wires['ok'], [[100, 300], [400, 300]])
        # Extremos conservados y codo insertado en el tramo oblicuo.
        self.assertEqual(wires['a4'], [[100, 100], [200, 100], [300, 100], [300, 200]])

    def test_repair_is_noop_on_valid_document(self):
        project = core.new_project('Valido')
        doc = project['sheets'][0]
        doc['wires'] = [make_wire((100, 100), (300, 200)), make_straight_wire((0, 0), (40, 20))]
        before = [dict(w) for w in doc['wires']]
        self.assertEqual(core.repair_wires(doc), 0)
        self.assertEqual(doc['wires'], before)


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

    def test_zoom_entry_selects_all_on_focus(self):
        entry = self.app.zoom_entry
        entry.focus_force()
        for _ in range(5):
            self.root.update()
        self.assertTrue(entry.selection_present())
        self.assertEqual(entry.selection_get(), self.app._zoom_var.get())

    def test_zoom_text_fits_box(self):
        self.assertEqual(self.app._zoom_text(71.178), '71')
        self.assertEqual(self.app._zoom_text(250), '250')
        self.assertEqual(self.app._zoom_text(5.25), '5.2')

    def test_toolbar_uses_logical_width(self):
        self.app._compact_toolbar = None
        self.app._s, old = 1.5, self.app._s
        try:
            self.app._responsive_toolbar(1920)  # 1920 px reales al 150 % = 1280 lógicos
            self.assertFalse(self.app._compact_toolbar[0], 'Con 1280 lógicos no cabe la barra completa')
        finally:
            self.app._s = old

    def test_save_repairs_zero_length_wire(self):
        self.app.doc['wires'].append({'id': 'cero', 'points': [[500, 500], [500, 500]]})
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(self.app._save_to(str(Path(tmp) / 'g.ework')))
            self.assertTrue((Path(tmp) / 'g.ework').exists())
        self.assertNotIn('cero', [w['id'] for w in self.app.doc['wires']])
        self.assertIn('corregidos', self.app._status_var.get())

    def test_save_and_save_as_buttons(self):
        import electrical_work
        self.assertEqual(self.app.save_as_button.cget('text'), 'Guardar como')
        with tempfile.TemporaryDirectory() as tmp:
            first = str(Path(tmp) / 'uno.ework')
            second = str(Path(tmp) / 'dos.ework')
            asked = []
            original = electrical_work.filedialog.asksaveasfilename
            electrical_work.filedialog.asksaveasfilename = lambda **kw: (asked.append(kw), first if len(asked) == 1 else second)[1]
            try:
                self.assertTrue(self.app.save_file())          # primera vez: pregunta
                self.assertTrue(self.app.save_file())          # después: directo
                self.assertEqual(len(asked), 1)
                self.app.save_as_button.invoke()               # Guardar como: pregunta
                self.assertEqual(len(asked), 2)
                self.assertEqual(asked[1]['initialfile'], 'uno.ework')
            finally:
                electrical_work.filedialog.asksaveasfilename = original
            self.assertEqual(self.app.filepath, second)
            self.assertTrue(Path(first).exists() and Path(second).exists())

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

"""Pruebas de las funciones de la revisión 8:
exportación (una hoja / todas / solo documentación), nomenclatura del PLC
por fabricante y guías de alineación al dibujar líneas."""
from __future__ import annotations

import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402
from core import (make_symbol, make_wire, plc_channel_name, plc_names,  # noqa: E402
                  annotation_positions, save_project, load_project, validate_document)
from documentation import documentation_rows  # noqa: E402

_clock = [1000]


def tick():
    _clock[0] += 1000
    return _clock[0]


class PlcNames(unittest.TestCase):
    def test_numberings(self):
        self.assertEqual([plc_channel_name('I', i) for i in (0, 7, 8)], ['I0.0', 'I0.7', 'I1.0'])
        self.assertEqual([plc_channel_name('X', i, 'octal') for i in (0, 7, 8, 9)], ['X0', 'X7', 'X10', 'X11'])
        self.assertEqual([plc_channel_name('X', i, 'decimal0') for i in (0, 9)], ['X0', 'X9'])
        self.assertEqual([plc_channel_name('I', i, 'decimal1') for i in (0, 9)], ['I1', 'I10'])

    def _plc(self, **names):
        el = make_symbol('plc_module', 600, 400, 'PLC1', plc_inputs=9, plc_outputs=3)
        el.update(names)
        return el

    def test_old_plc_keeps_i_q(self):
        el = self._plc()
        self.assertEqual(plc_names(el), ('I', 'Q', 'byte'))
        texts = {k: s[3] for k, s in annotation_positions(el)}
        self.assertEqual(texts['input:8'], 'I1.0')
        self.assertEqual(texts['output:0'], 'Q0.0')

    def test_custom_names_on_drawing_documentation_and_file(self):
        el = self._plc(plc_input_prefix='X', plc_output_prefix='Y', plc_numbering='octal')
        texts = {k: s[3] for k, s in annotation_positions(el)}
        self.assertEqual(texts['input:8'], 'X10')
        self.assertEqual(texts['output:2'], 'Y2')
        project = core.new_project('PLC')
        project['sheets'][0]['elements'] = [el]
        refs = [r['reference'] for r in documentation_rows(project)]
        self.assertIn('X10', refs)
        self.assertIn('Y2', refs)
        with tempfile.TemporaryDirectory() as tmp:
            save_project(project, Path(tmp) / 'p.ework')
            loaded = load_project(Path(tmp) / 'p.ework')
        self.assertEqual(plc_names(loaded['sheets'][0]['elements'][0]), ('X', 'Y', 'octal'))

    def test_invalid_names_rejected(self):
        doc = core.new_document()
        doc['elements'] = [self._plc(plc_input_prefix='', plc_output_prefix='Y', plc_numbering='octal')]
        with self.assertRaises(ValueError):
            validate_document(doc)
        doc['elements'] = [self._plc(plc_numbering='hexadecimal')]
        with self.assertRaises(ValueError):
            validate_document(doc)


class GuiFeatures(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Tkinter sin pantalla: {exc}')
        self.root.geometry('1400x900')
        from electrical_work import ElectricalWorkApp
        self.app = ElectricalWorkApp(self.root)
        self.root.update()

    def tearDown(self):
        if hasattr(self, 'root'):
            self.root.destroy()

    def test_alignment_guides_snap_to_existing_points(self):
        self.app.doc['wires'] = [make_wire((200, 300), (500, 300))]
        self.app._set_tool('wire')
        tol = 8 * self.app._s / self.app.zoom
        # Cerca de la vertical del extremo (500, 300), lejos de la horizontal.
        point, vref, href = self.app._align_point(500 + tol * 0.6, 520)
        self.assertEqual(point[0], 500)
        self.assertEqual(vref, (500, 300))
        self.assertIsNone(href)
        # Cerca de la horizontal y = 300.
        point, vref, href = self.app._align_point(800, 300 - tol * 0.6)
        self.assertEqual(point[1], 300)
        self.assertEqual(href[1], 300)
        # Las guías se dibujan en la vista previa.
        self.app._last_cursor = (500 + tol * 0.6, 520)
        self.app._draw_wire_overlay()
        self.assertTrue(self.app.canvas.find_withtag('wire-overlay'))

    def test_wire_click_uses_alignment(self):
        self.app.doc['wires'] = [make_wire((200, 300), (500, 300))]
        self.app.redraw()
        self.app._set_tool('wire')
        tol = 8 * self.app._s / self.app.zoom
        cv = self.app.canvas
        for x, y in ((700, 520), (500 + tol * 0.5, 600)):
            px, py = self.app._xy(x, y)
            wx, wy = round(px - cv.canvasx(0)), round(py - cv.canvasy(0))
            cv.event_generate('<Motion>', x=wx, y=wy)
            cv.event_generate('<ButtonPress-1>', x=wx, y=wy, time=tick())
            cv.event_generate('<ButtonRelease-1>', x=wx, y=wy, time=tick())
            self.root.update()
        new = self.app.doc['wires'][-1]['points']
        self.assertEqual(new[-1][0], 500)

    def test_symbol_placement_aligns_terminals_and_shows_ghost(self):
        self.app.doc['wires'] = [make_wire((500, 200), (500, 300))]
        self.app.redraw()
        self.app._set_tool('contact_no')
        tol = 8 * self.app._s / self.app.zoom
        cv = self.app.canvas
        px, py = self.app._xy(500 + tol * 0.6, 520)
        wx, wy = round(px - cv.canvasx(0)), round(py - cv.canvasy(0))
        cv.event_generate('<Motion>', x=wx, y=wy)
        self.root.update()
        self.assertTrue(cv.find_withtag('wire-overlay'), 'vista previa y guías visibles')
        cv.event_generate('<ButtonPress-1>', x=wx, y=wy, time=tick())
        cv.event_generate('<ButtonRelease-1>', x=wx, y=wy, time=tick())
        self.root.update()
        placed = self.app.doc['elements'][-1]
        self.assertEqual(placed['kind'], 'contact_no')
        self.assertIn(500, [p[0] for p in core.port_positions(placed)],
                      'un borne del símbolo queda en la vertical del cable')

    def _run_export(self, choose):
        import electrical_work
        self.app.project['sheets'].append(core.new_document())
        self.app.project['sheets'][1]['title'] = 'Potencia'
        self.app._refresh_sheets()
        calls = []
        orig = (electrical_work.export_project_pdf, electrical_work.filedialog.asksaveasfilename,
                electrical_work.messagebox.showinfo)
        electrical_work.export_project_pdf = lambda *a, **kw: (calls.append(kw), 1)[1]
        electrical_work.filedialog.asksaveasfilename = lambda **kw: (calls.append({'initialfile': kw['initialfile']}), '/tmp/x.pdf')[1]
        electrical_work.messagebox.showinfo = lambda *a, **kw: None
        try:
            self.root.after(50, lambda: self._click(choose))
            self.app.export_pdf_dialog()
            for _ in range(30):
                self.root.update()
                self.root.after(20)
        finally:
            (electrical_work.export_project_pdf, electrical_work.filedialog.asksaveasfilename,
             electrical_work.messagebox.showinfo) = orig
        return calls

    def _widgets(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._widgets(child)

    def _click(self, choose):
        top = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
        widgets = list(self._widgets(top))
        if choose == 'sheet2':
            combo = next(w for w in widgets if w.winfo_class() == 'TCombobox')
            combo.current(1)
            combo.event_generate('<<ComboboxSelected>>')
        else:
            text = {'all': 'Todas las hojas', 'docs': 'Solo la documentación'}[choose]
            next(w for w in widgets if isinstance(w, tk.Radiobutton) and w.cget('text').startswith(text)).invoke()
        next(w for w in widgets if isinstance(w, tk.Button) and w.cget('text') == 'Exportar PDF').invoke()

    def test_export_single_chosen_sheet(self):
        calls = self._run_export('sheet2')
        self.assertEqual(calls[0]['initialfile'], 'Esquema_hoja_002.pdf')
        self.assertEqual(calls[1]['sheet_indices'], [1])

    def test_export_all_sheets(self):
        calls = self._run_export('all')
        self.assertIsNone(calls[1]['sheet_indices'])

    def test_export_documentation_only(self):
        calls = self._run_export('docs')
        self.assertEqual(calls[0]['initialfile'], 'Documentacion.pdf')
        self.assertTrue(calls[1]['documentation_only'])


if __name__ == '__main__':
    unittest.main()

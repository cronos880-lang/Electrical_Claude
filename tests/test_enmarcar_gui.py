"""Regresión del marcado con el Puntero y del botón derecho (eventos reales de Tk).

Comportamiento pedido (V0.5.4 OPT):
- Puntero, botón izquierdo en vacío: arrastrar marca un recuadro de selección.
- Puntero, botón izquierdo sobre un objeto (o grupo marcado): lo mueve.
- Botón derecho arrastrando: desplaza la hoja ampliada (cualquier herramienta).
- Botón derecho sin arrastrar con objetos marcados: los borra (Ctrl+Z deshace).
- «Enmarcar» ya no figura en el desplegable de Líneas.

Ejecutar: python -m unittest discover -s tests -v
En Linux sin pantalla: xvfb-run -a python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import make_symbol, make_straight_wire
from electrical_work import ElectricalWorkApp

_clock = [1000]


def tick():
    # Marca de tiempo creciente: dos pulsaciones generadas no son doble clic.
    _clock[0] += 1000
    return _clock[0]


class TestMarcarConPuntero(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tkinter sin pantalla disponible: {exc}")
        self.root.geometry("1280x900")
        self.app = ElectricalWorkApp(self.root)
        self.root.update()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def _fixture(self):
        a = make_symbol("contact_no", 300, 220)
        b = make_symbol("contact_nc", 460, 290)
        c = make_symbol("contact_no", 900, 620)
        self.app.doc["elements"] = [a, b, c]
        self.app.doc["wires"] = []
        self.app.redraw()
        self.root.update()
        return a, b, c

    def _mouse_at_page(self, x, y):
        cv = self.app.canvas
        px, py = self.app._xy(x, y)
        return round(px - cv.canvasx(0)), round(py - cv.canvasy(0))

    def _left_drag(self, x1, y1, x2, y2):
        cv = self.app.canvas
        ax, ay = self._mouse_at_page(x1, y1)
        bx, by = self._mouse_at_page(x2, y2)
        mx, my = round((ax + bx) / 2), round((ay + by) / 2)
        cv.event_generate("<ButtonPress-1>", x=ax, y=ay, time=tick())
        cv.event_generate("<B1-Motion>", x=mx, y=my, time=tick())
        cv.event_generate("<B1-Motion>", x=bx, y=by, time=tick())
        cv.event_generate("<ButtonRelease-1>", x=bx, y=by, time=tick())
        self.root.update()

    def _marquee(self, x1, y1, x2, y2):
        cv = self.app.canvas
        ax, ay = self._mouse_at_page(x1, y1)
        bx, by = self._mouse_at_page(x2, y2)
        cv.event_generate("<ButtonPress-1>", x=ax, y=ay, time=tick())
        cv.event_generate("<B1-Motion>", x=round((ax + bx) / 2), y=round((ay + by) / 2), time=tick())
        self.assertIsNotNone(self.app.marquee_start)
        self.assertTrue(cv.find_withtag("selection-marquee"))
        cv.event_generate("<B1-Motion>", x=bx, y=by, time=tick())
        cv.event_generate("<ButtonRelease-1>", x=bx, y=by, time=tick())
        self.root.update()
        self.assertIsNone(self.app.marquee_start)
        self.assertEqual(self.app.tool, "select")

    def _right_click(self, x, y):
        cv = self.app.canvas
        px, py = self._mouse_at_page(x, y)
        cv.event_generate("<ButtonPress-3>", x=px, y=py, time=tick())
        cv.event_generate("<ButtonRelease-3>", x=px, y=py, time=tick())
        self.root.update()

    def test_enmarcar_removed_from_lines_group(self):
        self.assertNotIn("select_box", self.app._groups["wire_group"])
        self.assertEqual(self.app._groups["wire_group"],
                         ("wire_straight", "wire", "wire_rectangle"))

    def test_pointer_marquee_selects_two_without_panning(self):
        a, b, c = self._fixture()
        self.assertEqual(self.app.tool, "select")
        canvas = self.app.canvas
        offset = (canvas.canvasx(0), canvas.canvasy(0))
        self._marquee(245, 160, 525, 355)
        expected = {("element", a["id"]), ("element", b["id"])}
        self.assertEqual(self.app._selection_items(), expected)
        self.assertEqual((canvas.canvasx(0), canvas.canvasy(0)), offset)
        self.assertFalse(self.app.dirty, "Marcar no modifica el proyecto")
        # Un segundo recuadro inmediato sustituye la selección.
        self._marquee(250, 165, 355, 255)
        self.assertEqual(self.app._selection_items(), {("element", a["id"])})

    def test_marquee_selects_crossing_cable(self):
        self._fixture()
        wire = make_straight_wire((200, 430), (760, 430))
        self.app.doc["wires"].append(wire)
        self.app.redraw()
        self.root.update()
        self._marquee(350, 400, 510, 460)
        self.assertIn(("wire", wire["id"]), self.app._selection_items())

    def test_left_click_on_empty_clears_selection(self):
        a, b, c = self._fixture()
        self._marquee(245, 160, 525, 355)
        self.assertTrue(self.app._selection_items())
        cv = self.app.canvas
        px, py = self._mouse_at_page(700, 450)
        cv.event_generate("<ButtonPress-1>", x=px, y=py, time=tick())
        cv.event_generate("<ButtonRelease-1>", x=px, y=py, time=tick())
        self.root.update()
        self.assertEqual(self.app._selection_items(), set())

    def test_marked_group_moves_with_left_drag(self):
        a, b, c = self._fixture()
        self._marquee(245, 160, 525, 355)
        before = {(e["id"]): (e["x"], e["y"]) for e in self.app.doc["elements"]}
        self._left_drag(a["x"], a["y"], a["x"] + 40, a["y"] + 20)
        after = {(e["id"]): (e["x"], e["y"]) for e in self.app.doc["elements"]}
        self.assertEqual(after[a["id"]], (before[a["id"]][0] + 40, before[a["id"]][1] + 20))
        self.assertEqual(after[b["id"]], (before[b["id"]][0] + 40, before[b["id"]][1] + 20))
        self.assertEqual(after[c["id"]], before[c["id"]])

    def test_zoom_left_drag_marks_and_right_drag_pans(self):
        a, b, c = self._fixture()
        self.app.set_zoom(240)
        self.app.canvas.xview_moveto(0)
        self.app.canvas.yview_moveto(0)
        self.root.update()
        cv = self.app.canvas
        before = (cv.canvasx(0), cv.canvasy(0))
        self._marquee(250, 170, 352, 263)
        self.assertEqual(self.app._selection_items(), {("element", a["id"])})
        self.assertEqual(before, (cv.canvasx(0), cv.canvasy(0)), "Marcar no desplaza la hoja")
        # Botón derecho arrastrando: desplaza la vista, no cambia nada más.
        cv.event_generate("<ButtonPress-3>", x=600, y=500, time=tick())
        for step in range(1, 6):
            cv.event_generate("<B3-Motion>", x=600 - step * 40, y=500 - step * 30, time=tick())
        cv.event_generate("<ButtonRelease-3>", x=400, y=350, time=tick())
        self.root.update()
        self.assertNotEqual(before, (cv.canvasx(0), cv.canvasy(0)), "El botón derecho desplaza")
        self.assertEqual(self.app._selection_items(), {("element", a["id"])},
                         "Desplazar no borra ni cambia la selección")
        self.assertEqual(len(self.app.doc["elements"]), 3)
        self.assertFalse(self.app.dirty)

    def test_right_click_deletes_marked_and_undo_restores(self):
        a, b, c = self._fixture()
        self._marquee(245, 160, 525, 355)
        self._right_click(700, 450)
        ids = {e["id"] for e in self.app.doc["elements"]}
        self.assertEqual(ids, {c["id"]})
        self.assertEqual(self.app._selection_items(), set())
        self.assertTrue(self.app.dirty)
        self.app.undo()
        self.root.update()
        self.assertEqual({e["id"] for e in self.app.doc["elements"]}, {a["id"], b["id"], c["id"]})

    def test_right_click_without_selection_deletes_nothing(self):
        self._fixture()
        self._right_click(700, 450)
        self.assertEqual(len(self.app.doc["elements"]), 3)
        self.assertFalse(self.app.dirty)

    def test_right_click_with_drawing_tool_cancels_wire(self):
        self._fixture()
        self.app._set_tool("wire")
        cv = self.app.canvas
        px, py = self._mouse_at_page(600, 500)
        cv.event_generate("<ButtonPress-1>", x=px, y=py, time=tick())
        cv.event_generate("<ButtonRelease-1>", x=px, y=py, time=tick())
        self.root.update()
        self.assertIsNotNone(self.app.pending_wire)
        self._right_click(650, 500)
        self.assertIsNone(self.app.pending_wire)
        self.assertEqual(len(self.app.doc["elements"]), 3)


if __name__ == "__main__":
    unittest.main()

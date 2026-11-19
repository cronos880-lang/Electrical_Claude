"""Banco de medidas de rendimiento de Electrical Work (sin datos del usuario).

Genera esquemas sintéticos deterministas y mide, con eventos reales de
Tkinter, las operaciones que más afectan a la fluidez:

    python tests/bench_rendimiento.py            (resultado en pantalla)
    python tests/bench_rendimiento.py --json f   (además guarda JSON)

Todas las medidas incluyen el procesamiento de Tk (``update``), es decir,
el tiempo hasta que la pantalla queda actualizada. No modifica archivos del
usuario: los guardados se hacen en una carpeta temporal.
"""
from __future__ import annotations

import gc
import json
import os
import statistics
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402
from core import make_symbol, make_wire, port_positions, save_project, load_project  # noqa: E402
from electrical_work import ElectricalWorkApp  # noqa: E402

VERTICAL_KINDS = [k for k in core.SYMBOL_NAMES
                  if k not in ('plc_module', 'selector_multi', 'text', 'image')]


def build_sheet(doc, cols, rows, dx, dy):
    """Escalera de símbolos conectados por cables entre bornes reales."""
    scale = doc.get('drawing_scale', 1.0)
    elements, wires = [], []
    kinds = [k for k in VERTICAL_KINDS
             if len(port_positions(make_symbol(k, 0, 0, draw_scale=scale))) == 2
             and port_positions(make_symbol(k, 0, 0, draw_scale=scale))[0][0] == 0]
    n = 0
    for c in range(cols):
        prev = None
        for r in range(rows):
            x = 60 + c * dx
            y = 90 + r * dy
            el = make_symbol(kinds[n % len(kinds)], x, y, f'K{n}', draw_scale=scale)
            n += 1
            elements.append(el)
            ports = port_positions(el)
            if prev is not None:
                wires.append(make_wire(prev, ports[0]))
            prev = ports[-1]
    # Barras horizontales superior/inferior que unen columnas (puntos de unión).
    for c in range(cols - 1):
        top_a = port_positions(elements[c * rows])[0]
        top_b = port_positions(elements[(c + 1) * rows])[0]
        wires.append(make_wire((top_a[0], top_a[1] - 20), (top_b[0], top_b[1] - 20)))
    doc['elements'] = elements
    doc['wires'] = wires
    return elements, wires


class Bench:
    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry('1600x950')
        self.app = ElectricalWorkApp(self.root)
        self.root.update()

    def close(self):
        self.root.destroy()

    def flush(self):
        self.root.update()

    def page_to_widget(self, x, y):
        cv = self.app.canvas
        px, py = self.app._xy(x, y)
        return round(px - cv.canvasx(0)), round(py - cv.canvasy(0))

    def time_it(self, func, repeat=5):
        samples = []
        for _ in range(repeat):
            t = time.perf_counter()
            func()
            self.flush()
            samples.append((time.perf_counter() - t) * 1000)
        return samples

    def drag(self, start, steps, step=(10, 0)):
        """Pulsa en ``start`` (página) y arrastra ``steps`` pasos de rejilla."""
        cv = self.app.canvas
        x, y = self.page_to_widget(*start)
        cv.event_generate('<ButtonPress-1>', x=x, y=y, time=tick())
        self.flush()
        samples = []
        for i in range(1, steps + 1):
            tx, ty = self.page_to_widget(start[0] + step[0] * i, start[1] + step[1] * i)
            t = time.perf_counter()
            cv.event_generate('<B1-Motion>', x=tx, y=ty, time=tick())
            self.flush()
            samples.append((time.perf_counter() - t) * 1000)
        cv.event_generate('<ButtonRelease-1>', x=tx, y=ty, time=tick())
        t = time.perf_counter()
        self.flush()
        release = (time.perf_counter() - t) * 1000
        return samples, release


_clock = [1000]


def tick():
    """Marca de tiempo creciente: evita que Tk tome dos pulsaciones
    generadas seguidas como doble clic (abriría un diálogo)."""
    _clock[0] += 1000
    return _clock[0]


def peak_rss_mb():
    """Memoria máxima del proceso (Windows y Linux, sin dependencias)."""
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except ImportError:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                        ('a', ctypes.c_size_t), ('b', ctypes.c_size_t), ('c', ctypes.c_size_t),
                        ('d', ctypes.c_size_t), ('e', ctypes.c_size_t), ('f', ctypes.c_size_t)]
        pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                 ctypes.byref(pmc), pmc.cb)
        return round(pmc.PeakWorkingSetSize / 1e6, 1)


def summary(samples):
    s = sorted(samples)
    return {'media_ms': round(statistics.mean(s), 2),
            'mediana_ms': round(statistics.median(s), 2),
            'p95_ms': round(s[min(len(s) - 1, int(len(s) * .95))], 2),
            'max_ms': round(s[-1], 2), 'n': len(s)}


def run_case(name, cols, rows, dx, dy, zoom):
    b = Bench()
    app = b.app
    elements, wires = build_sheet(app.doc, cols, rows, dx, dy)
    app._symbol_cache.clear() if hasattr(app, '_symbol_cache') else None
    app.set_zoom(zoom)
    app.canvas.xview_moveto(0)
    app.canvas.yview_moveto(0)
    t = time.perf_counter()
    app.redraw(); b.flush()
    first = (time.perf_counter() - t) * 1000
    result = {'caso': name, 'zoom': zoom, 'simbolos': len(elements), 'cables': len(wires),
              'items_canvas': len(app.canvas.find_all()),
              'redibujado_inicial_ms': round(first, 2),
              'redibujado_completo': summary(b.time_it(app.redraw, 8))}
    # Seleccionar con un clic un símbolo (redibujado tras la selección).
    target = elements[len(elements) // 2]
    tx, ty = b.page_to_widget(target['x'], target['y'])

    clicks = []
    for i in range(5):
        if i % 2:  # alternar: deseleccionar (fondo) / seleccionar símbolo
            app.selected = None; app.redraw(); b.flush()
        t = time.perf_counter()
        app.canvas.event_generate('<ButtonPress-1>', x=tx, y=ty, time=tick())
        app.canvas.event_generate('<ButtonRelease-1>', x=tx, y=ty, time=tick())
        b.flush()
        clicks.append((time.perf_counter() - t) * 1000)
    result['clic_seleccion'] = summary(clicks)
    # Arrastre de un símbolo conectado.
    app.selected = None; app.multi_selected.clear(); app.redraw(); b.flush()
    samples, rel = b.drag((target['x'], target['y']), 30)
    result['arrastre_simbolo'] = summary(samples)
    result['arrastre_simbolo_soltar_ms'] = round(rel, 2)
    # Arrastre de un grupo (dos columnas completas con sus cables).
    group = {('element', e['id']) for e in elements[:2 * rows]}
    group |= {('wire', w['id']) for w in wires[:2 * (rows - 1)]}
    first_el = elements[0]
    app.selected = None
    app.multi_selected = set(group)
    app.redraw(); b.flush()
    samples, rel = b.drag((first_el['x'], first_el['y']), 30, (10, 0))
    result['arrastre_grupo'] = summary(samples)
    result['arrastre_grupo_objetos'] = len(group)
    result['arrastre_grupo_soltar_ms'] = round(rel, 2)
    # Enmarcar (rectángulo de selección).
    app.selected = None; app.multi_selected.clear()
    app._set_tool('select'); app.redraw(); b.flush()
    samples, rel = b.drag((30, 40), 30, (12, 8))
    result['enmarcar'] = summary(samples)
    result['enmarcar_soltar_ms'] = round(rel, 2)
    app._set_tool('select')
    # Zoom con la rueda.
    cv = app.canvas

    def wheel():
        cv.event_generate('<Button-4>' if wheel.n % 2 == 0 else '<Button-5>', x=400, y=300)
        wheel.n += 1
    wheel.n = 0
    result['zoom_rueda'] = summary(b.time_it(wheel, 6))
    # Movimiento del ratón con la herramienta de cable (vista previa).
    app.set_zoom(zoom); app._set_tool('wire'); b.flush()

    def motion():
        motion.n += 1
        cv.event_generate('<Motion>', x=300 + motion.n * 3, y=300)
    motion.n = 0
    result['raton_cable'] = summary(b.time_it(motion, 20))
    app._set_tool('select')
    b.close()
    return result


def run_io(cols, rows, dx, dy):
    b = Bench()
    build_sheet(b.app.doc, cols, rows, dx, dy)
    project = b.app.project
    b.close()
    project['sheets'] = [project['sheets'][0]] * 1
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'bench.ework')
        t = time.perf_counter(); save_project(project, path); save = (time.perf_counter() - t) * 1000
        t = time.perf_counter(); load_project(path); load = (time.perf_counter() - t) * 1000
        size = os.path.getsize(path)
    return {'guardar_ms': round(save, 2), 'cargar_ms': round(load, 2), 'bytes': size}


def main():
    out = None
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
    t = time.perf_counter()
    b = Bench(); b.flush(); b.close()
    startup = (time.perf_counter() - t) * 1000
    cases = [
        ('mediano', 12, 5, 100, 150, 100),
        ('grande', 22, 7, 55, 115, 100),
        ('grande', 22, 7, 55, 115, 250),
    ]
    results = {'python': sys.version.split()[0], 'tk': tk.TkVersion,
               'arranque_ms': round(startup, 1), 'casos': []}
    for case in cases:
        gc.collect()
        results['casos'].append(run_case(*case))
        print(json.dumps(results['casos'][-1], ensure_ascii=False), flush=True)
    results['archivo'] = run_io(22, 7, 55, 115)
    results['memoria_pico_mb'] = peak_rss_mb()
    print(json.dumps({k: v for k, v in results.items() if k != 'casos'}, ensure_ascii=False))
    if out:
        Path(out).write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()

"""Nitidez en pantallas con escalado de Windows (125 %, 150 %, ...).

Sin esto, Python/Tk no se declara compatible con DPI y Windows dibuja la
ventana a baja resolución y la amplía como una imagen: todo se ve borroso.

Con ``activar_dpi()`` (antes de crear la ventana) el programa recibe los
píxeles reales. Las fuentes en puntos se adaptan solas; ``instalar(root)``
multiplica además las medidas de la interfaz expresadas en píxeles
(márgenes, bordes, alturas de barras, tamaño de los iconos) por el factor de
escala, de modo que la ventana conserva exactamente su tamaño visual pero se
dibuja con todo el detalle de la pantalla.

Desactivar (volver al comportamiento anterior): crear un archivo vacío
``SIN_DPI.txt`` junto al programa, o la variable de entorno ``EW_DPI=0``.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk

ESCALA = 1.0
_INSTALADO = False

# Opciones en píxeles en cualquier widget o gestor de geometría.
_SIEMPRE = {'padx', 'pady', 'ipadx', 'ipady', 'bd', 'borderwidth',
            'highlightthickness', 'wraplength'}
# Anchura/altura solo son píxeles en estos widgets (en botones, etiquetas o
# entradas son caracteres y no se tocan).
_PIXELES_WH = {'frame', 'canvas', 'toplevel', 'labelframe'}


def desactivado():
    carpeta = os.path.dirname(os.path.abspath(__file__))
    return (os.environ.get('EW_DPI', '1') == '0'
            or os.path.exists(os.path.join(carpeta, 'SIN_DPI.txt')))


def activar_dpi():
    """Declarar el proceso compatible con DPI (solo Windows)."""
    if sys.platform != 'win32' or desactivado():
        return False
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # DPI de sistema
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
        return True
    except Exception:
        return False


def px(valor):
    """Escala una medida de interfaz en píxeles."""
    if ESCALA == 1.0:
        return valor
    return int(round(valor * ESCALA))


def _escalar_valor(valor):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return int(round(valor * ESCALA))
    if isinstance(valor, (tuple, list)):
        return type(valor)(_escalar_valor(v) for v in valor)
    if isinstance(valor, str):
        try:
            return str(int(round(float(valor) * ESCALA)))
        except ValueError:
            return valor
    return valor


def _escalar(opciones, nombre_widget=None):
    if not opciones:
        return opciones
    salida = dict(opciones)
    for clave, valor in opciones.items():
        k = clave.rstrip('_')
        if k in _SIEMPRE or (k in ('width', 'height') and nombre_widget in _PIXELES_WH):
            salida[clave] = _escalar_valor(valor)
    return salida


def instalar(root):
    """Calcula el factor de escala y adapta las medidas en píxeles."""
    global ESCALA, _INSTALADO
    try:
        factor = root.winfo_fpixels('1i') / 96.0
    except tk.TclError:
        factor = 1.0
    if desactivado() or abs(factor - 1.0) < 0.05:
        ESCALA = 1.0
        return ESCALA
    ESCALA = factor
    if _INSTALADO:
        return ESCALA
    _INSTALADO = True

    base_init = tk.BaseWidget.__init__

    def init(self, master, widgetName, cnf={}, kw={}, extra=()):
        nombre = str(widgetName).split('::')[-1]
        return base_init(self, master, widgetName, _escalar(cnf, nombre),
                         _escalar(kw, nombre), extra)
    tk.BaseWidget.__init__ = init

    base_conf = tk.Misc.configure

    def configure(self, cnf=None, **kw):
        nombre = getattr(self, 'widgetName', None)
        nombre = str(nombre).split('::')[-1] if nombre else None
        if isinstance(cnf, dict):
            cnf = _escalar(cnf, nombre)
        return base_conf(self, cnf, **_escalar(kw, nombre))
    tk.Misc.configure = tk.Misc.config = configure

    for clase, metodo in ((tk.Pack, 'pack_configure'), (tk.Grid, 'grid_configure')):
        original = getattr(clase, metodo)

        def gestor(self, cnf={}, _orig=original, **kw):
            return _orig(self, _escalar(cnf), **_escalar(kw))
        setattr(clase, metodo, gestor)
        if metodo == 'pack_configure':
            clase.pack = gestor
        else:
            clase.grid = gestor
    return ESCALA

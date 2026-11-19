"""Renderizado de pantalla suavizado de las formas vectoriales del editor.

El motor geométrico y los PDF/SVG siguen siendo vectoriales; este módulo
únicamente mejora la representación en pantalla. Pillow es opcional: cuando
no está instalado la interfaz usa el Canvas clásico.

Versión optimizada (experimental):

* Trazos con un único grosor entero de píxel en todo el esquema (cables y
  símbolos) y alineados con la rejilla de píxeles: las líneas horizontales y
  verticales salen nítidas, sin bordes borrosos, y las curvas y oblicuas
  quedan suavizadas por sobremuestreo 4x con promedio exacto (``reduce``),
  sin halos.
* Textos dibujados a resolución final con el suavizado nativo de FreeType
  (más nítidos que el texto reducido desde 4x).
* Mapas de bits independientes de la posición: el mismo símbolo desplazado
  reutiliza su imagen, por lo que arrastrar no vuelve a rasterizar.
* Fuentes resueltas una sola vez y conservadas en memoria.

Ninguna función modifica coordenadas del proyecto: todo el ajuste se hace
sobre píxeles de pantalla.
"""
from __future__ import annotations
import math
import os

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageColor
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

SS = 4
# Grosor nominal (unidades de página) de cables y símbolos en pantalla.
STROKE = 1.6
_PAD = 4

_WIN_FONTS = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
_FONT_FILES = {
    # familia: (normal, negrita) en Windows
    'segoe ui': ('segoeui.ttf', 'segoeuib.ttf'),
    'arial': ('arial.ttf', 'arialbd.ttf'),
    'calibri': ('calibri.ttf', 'calibrib.ttf'),
    'tahoma': ('tahoma.ttf', 'tahomabd.ttf'),
    'verdana': ('verdana.ttf', 'verdanab.ttf'),
    'times new roman': ('times.ttf', 'timesbd.ttf'),
    'courier new': ('cour.ttf', 'courbd.ttf'),
    'consolas': ('consola.ttf', 'consolab.ttf'),
    'helvetica': ('arial.ttf', 'arialbd.ttf'),
}
_FALLBACKS = (
    ('segoeui.ttf', 'segoeuib.ttf'), ('arial.ttf', 'arialbd.ttf'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
     '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
    ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'),
)
_font_paths = {}
_font_objects = {}


def stroke_px(zoom, stroke=STROKE):
    """Grosor uniforme en píxeles enteros para la escala de pantalla."""
    return max(1, int(round(stroke * zoom)))


def align(value, width):
    """Coloca el eje de un trazo ortogonal en la rejilla de píxeles."""
    if width % 2:
        return math.floor(value) + .5
    return float(round(value))


def _candidate_files(family, bold):
    key = str(family or '').strip().lower()
    names = []
    if key in _FONT_FILES:
        names.append(_FONT_FILES[key][1 if bold else 0])
    if family:
        names.append(str(family))
    names += [pair[1 if bold else 0] for pair in _FALLBACKS]
    result = []
    for name in names:
        if os.path.isabs(name) or os.sep in name or '/' in name:
            result.append(name)
        else:
            win = os.path.join(_WIN_FONTS, name)
            if os.path.exists(win):
                result.append(win)
            result.append(name)
    return result


def _font(size, family=None, bold=False):
    """Fuente TrueType en caché (tamaño en píxeles, admite fracciones)."""
    size = max(1.0, round(float(size), 2))
    key = (family, bold, size)
    font = _font_objects.get(key)
    if font is not None:
        return font
    path_key = (family, bold)
    path = _font_paths.get(path_key)
    if path is None:
        for candidate in _candidate_files(family, bold):
            try:
                ImageFont.truetype(candidate, 10)
            except (OSError, ValueError):
                continue
            path = candidate
            break
        _font_paths[path_key] = path or ''
    try:
        font = ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)
    except (OSError, ValueError):
        font = ImageFont.load_default(size=size)
    if len(_font_objects) > 400:
        _font_objects.clear()
    _font_objects[key] = font
    return font


_colors = {}


def _color(value):
    rgb = _colors.get(value)
    if rgb is None:
        try:
            rgb = ImageColor.getrgb(value)[:3]
        except (TypeError, ValueError):
            rgb = (32, 50, 72)
        _colors[value] = rgb
    return rgb


def _dashed(draw, a, b, ink, width, dash=5 * SS, gap=3 * SS):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if not length:
        return
    x, y = dx / length, dy / length
    p = 0.0
    while p < length:
        q = min(length, p + dash)
        draw.line((a[0] + x * p, a[1] + y * p, a[0] + x * q, a[1] + y * q), fill=ink, width=width)
        p = q + gap


def shapes_key(shapes, ox, oy):
    """Representación de las formas relativa al origen (clave de caché)."""
    out = []
    for shape in shapes:
        typ = shape[0]
        if typ in ('line', 'dashline'):
            out.append((typ, round(shape[1] - ox, 4), round(shape[2] - oy, 4),
                        round(shape[3] - ox, 4), round(shape[4] - oy, 4)))
        elif typ in ('polygon', 'filledpolygon'):
            out.append((typ, tuple((round(x - ox, 4), round(y - oy, 4)) for x, y in shape[1])))
        elif typ in ('circle', 'dot'):
            out.append((typ, round(shape[1] - ox, 4), round(shape[2] - oy, 4), shape[3]))
        elif typ in ('text', 'textcenter', 'textend'):
            out.append((typ, round(shape[1] - ox, 4), round(shape[2] - oy, 4)) + tuple(shape[3:]))
    return tuple(out)


def origin_phase(ox, oy, zoom):
    """Parte entera y fraccionaria (en píxeles) del origen de un elemento."""
    gx, gy = ox * zoom, oy * zoom
    ix, iy = math.floor(gx), math.floor(gy)
    return ix, iy, round(gx - ix, 3), round(gy - iy, 3)


def _text_box(shape, zoom):
    x, y = shape[1:3]
    size = shape[4]
    approx = max(12, len(str(shape[3])) * size * .7)
    return [(x - approx, y - size), (x + approx, y + size)]


def render(shapes, zoom, ink='#21364c', width=None, origin=(0, 0), stroke=STROKE):
    """Rasteriza formas vectoriales con suavizado.

    Devuelve ``(PIL RGBA, left, top)`` donde ``left``/``top`` son relativos
    a ``floor(origin*zoom)`` en píxeles de página (sin desplazamiento de la
    vista). El resultado solo depende de la geometría relativa al origen y de
    la fracción de píxel del origen, por lo que puede reutilizarse al mover.
    """
    if not AVAILABLE or not shapes:
        return None
    if width is None:
        width = stroke_px(zoom, stroke)
    ox, oy = origin
    _ix, _iy, fx, fy = origin_phase(ox, oy, zoom)

    def local(x, y):
        return fx + (x - ox) * zoom, fy + (y - oy) * zoom

    bounds = []
    for shape in shapes:
        typ = shape[0]
        if typ in ('line', 'dashline'):
            bounds += [local(*shape[1:3]), local(*shape[3:5])]
        elif typ in ('polygon', 'filledpolygon'):
            bounds += [local(*p) for p in shape[1]]
        elif typ in ('circle', 'dot'):
            x, y, r = shape[1:4]
            bounds += [local(x - r, y - r), local(x + r, y + r)]
        elif typ in ('text', 'textend', 'textcenter'):
            bounds += [local(*p) for p in _text_box(shape, 1)]
    if not bounds:
        return None
    pad = _PAD + width
    left = math.floor(min(p[0] for p in bounds)) - pad
    top = math.floor(min(p[1] for p in bounds)) - pad
    right = math.ceil(max(p[0] for p in bounds)) + pad
    bottom = math.ceil(max(p[1] for p in bounds)) + pad
    w = max(1, right - left)
    h = max(1, bottom - top)
    # Protección frente a capas desmesuradas en elementos corruptos.
    if w * h > 3_500_000:
        return None
    image = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    linecolor = (*_color(ink), 255)
    white = (255, 255, 255, 255)
    thick = width * SS

    def px(x, y):
        a, b = local(x, y)
        return a - left, b - top

    half = thick / 2

    def bar(a, b):
        """Tramo ortogonal (coordenadas continuas ya alineadas) como
        rectángulo de cobertura exacta; extremos prolongados medio grosor."""
        x1, x2 = sorted((a[0] * SS, b[0] * SS))
        y1, y2 = sorted((a[1] * SS, b[1] * SS))
        x1, y1, x2, y2 = (round(x1 - half), round(y1 - half),
                          round(x2 + half), round(y2 + half))
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=linecolor)

    def oblique(a, b, dashed=False):
        # Pillow toma como coordenada el centro del píxel: -0,5 en SS.
        a = (a[0] * SS - .5, a[1] * SS - .5)
        b = (b[0] * SS - .5, b[1] * SS - .5)
        if dashed:
            _dashed(draw, a, b, linecolor, thick)
            return
        draw.line((*a, *b), fill=linecolor, width=thick)
        for cx, cy in (a, b):
            draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=linecolor)

    def segment(a, b, dashed=False):
        a, b = list(a), list(b)
        vertical = abs(a[0] - b[0]) < 1e-6
        horizontal = abs(a[1] - b[1]) < 1e-6
        if vertical:
            a[0] = b[0] = align(a[0], width)
        if horizontal:
            a[1] = b[1] = align(a[1], width)
        if (vertical or horizontal) and not dashed:
            bar(a, b)
        else:
            oblique(a, b, dashed)

    def ellipse(cx, cy, r, **kw):
        cx, cy = cx * SS - .5, cy * SS - .5
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), **kw)

    texts = []
    for shape in shapes:
        typ = shape[0]
        if typ in ('line', 'dashline'):
            segment(px(*shape[1:3]), px(*shape[3:5]), typ == 'dashline')
        elif typ in ('polygon', 'filledpolygon'):
            pts = [list(px(*point)) for point in shape[1]]
            ortho = all(abs(p[0] - q[0]) < 1e-6 or abs(p[1] - q[1]) < 1e-6
                        for p, q in zip(pts, pts[1:] + pts[:1]))
            if ortho:
                for p in pts:
                    p[0] = align(p[0], width)
                    p[1] = align(p[1], width)
            fill = linecolor if typ == 'filledpolygon' else white
            # Relleno opaco coherente con el Canvas clásico, el SVG y el PDF.
            draw.polygon([(p[0] * SS - .5, p[1] * SS - .5) for p in pts], fill=fill)
            if typ != 'filledpolygon':
                for p, q in zip(pts, pts[1:] + pts[:1]):
                    segment(p, q)
        elif typ in ('circle', 'dot'):
            x, y, r = shape[1:4]
            cx, cy = px(x, y)
            cx, cy = align(cx, width), align(cy, width)
            radius = r * zoom * SS
            if typ == 'dot':
                ellipse(cx, cy, radius, fill=linecolor)
            else:
                # Mismo criterio que la V0.5.3: el trazo queda dentro del radio,
                # de modo que bornes y anillos conservan su tamaño en pantalla.
                ellipse(cx, cy, radius, fill=white, outline=linecolor, width=thick)
        elif typ in ('text', 'textcenter', 'textend'):
            texts.append(shape)
    image = image.reduce(SS)
    if texts:
        draw = ImageDraw.Draw(image)
        for shape in texts:
            typ, x, y, label, size, color, *family = shape
            xx, yy = px(x, y)
            draw.text((xx, yy), str(label), font=_font(size * zoom, family[0] if family else None),
                      fill=(*_color(color), 255), anchor={'text': 'lm', 'textcenter': 'mm', 'textend': 'rm'}[typ])
    return image, left, top


def render_label(shape, zoom, origin=(0, 0)):
    """Texto suavizado a resolución final: ``(PIL RGBA, left, top)``."""
    if not AVAILABLE:
        return None
    typ, x, y, label, size, color, *family = shape
    if label is None or str(label) == '':
        return None
    ox, oy = origin
    _ix, _iy, fx, fy = origin_phase(ox, oy, zoom)
    font = _font(size * zoom, family[0] if family else None)
    anchor = {'text': 'lm', 'textcenter': 'mm', 'textend': 'rm'}[typ]
    lx, ly = fx + (x - ox) * zoom, fy + (y - oy) * zoom
    probe = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    x1, y1, x2, y2 = probe.textbbox((lx, ly), str(label), font=font, anchor=anchor)
    left = math.floor(x1) - 2
    top = math.floor(y1) - 2
    w = max(2, math.ceil(x2) + 2 - left)
    h = max(2, math.ceil(y2) + 2 - top)
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((lx - left, ly - top), str(label), font=font,
                             fill=(*_color(color), 255), anchor=anchor)
    return img, left, top


# --- Compatibilidad con la API de la V0.5.3 (coordenadas absolutas) ---------

def symbol_bitmap(shapes, zoom, ink='#21364c', stroke=STROKE):
    """Return (PIL RGBA, left, top) en píxeles de página absolutos."""
    result = render(shapes, zoom, ink, stroke=stroke)
    return result


def label_bitmap(shape, zoom):
    return render_label(shape, zoom)


def to_tk(bitmap):
    if not AVAILABLE:
        return None
    return ImageTk.PhotoImage(bitmap)


# --- Iconos de la interfaz suavizados ---------------------------------------

class IconPainter:
    """Imita las llamadas ``create_*`` del Canvas de Tk usadas en los iconos,
    pero dibuja con suavizado (sobremuestreo 4x). Mismas formas, coordenadas
    y colores que el dibujo original; solo mejora la definición."""

    def __init__(self, width, height, bg):
        self.w, self.h = int(width), int(height)
        self.image = Image.new('RGBA', (self.w * SS, self.h * SS), (*_color(bg), 255))
        self.draw = ImageDraw.Draw(self.image)
        self.texts = []

    @staticmethod
    def _flat(points):
        if len(points) == 1 and isinstance(points[0], (list, tuple)):
            points = points[0]
        flat = []
        for p in points:
            if isinstance(p, (list, tuple)):
                flat.extend(p)
            else:
                flat.append(p)
        return [(flat[i] * SS, flat[i + 1] * SS) for i in range(0, len(flat) - 1, 2)]

    def _cap(self, p, width, ink):
        r = width * SS / 2
        self.draw.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=ink)

    def create_line(self, *points, fill='black', width=1, capstyle='butt', joinstyle='miter',
                    dash=None, **_):
        pts = [(x / SS, y / SS) for x, y in self._flat(points)]
        ink = (*_color(fill), 255)
        # Grosor entero y tramos horizontales/verticales alineados al píxel:
        # trazo nítido (sin la franja gris de 2 px de un grosor 1,45 suavizado).
        w = max(1, int(round(float(width))))
        if dash:
            on, off = (dash[0], dash[1]) if len(dash) > 1 else (dash[0], dash[0])
            for a, b in zip(pts, pts[1:]):
                _dashed(self.draw, (a[0] * SS, a[1] * SS), (b[0] * SS, b[1] * SS),
                        ink, w * SS, on * SS, off * SS)
            return
        half = w * SS / 2
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6:
                x1, x2 = sorted((a[0], b[0]))
                y1, y2 = sorted((a[1], b[1]))
                if abs(a[0] - b[0]) < 1e-6:
                    x1 = x2 = align(a[0], w)
                else:
                    y1 = y2 = align(a[1], w)
                ext = half if capstyle != 'butt' or len(pts) > 2 else 0
                self.draw.rectangle((round(x1 * SS - half - (ext if y1 == y2 else 0)),
                                     round(y1 * SS - half - (ext if x1 == x2 else 0)),
                                     round(x2 * SS + half + (ext if y1 == y2 else 0)) - 1,
                                     round(y2 * SS + half + (ext if x1 == x2 else 0)) - 1), fill=ink)
            else:
                A = (a[0] * SS - .5, a[1] * SS - .5)
                B = (b[0] * SS - .5, b[1] * SS - .5)
                self.draw.line((A, B), fill=ink, width=w * SS)
                if capstyle == 'round' or joinstyle == 'round':
                    for p in (A, B):
                        self._cap(p, w, ink)

    def create_rectangle(self, x1, y1, x2, y2, fill='', outline='black', width=1, **_):
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        if fill:
            self.draw.polygon([(x * SS, y * SS) for x, y in pts], fill=(*_color(fill), 255))
        if outline:
            self.create_line(*pts, pts[0], fill=outline, width=width, capstyle='projecting')

    def create_oval(self, x1, y1, x2, y2, fill='', outline='black', width=1, **_):
        half = max(1, int(round(float(width)))) * SS / 2 if outline else 0
        box = (x1 * SS - half, y1 * SS - half, x2 * SS + half, y2 * SS + half)
        self.draw.ellipse(box, fill=(*_color(fill), 255) if fill else None,
                          outline=(*_color(outline), 255) if outline else None,
                          width=max(1, round(2 * half)) if outline else 0)

    def create_polygon(self, *points, fill='black', outline='', width=1, **_):
        pts = self._flat(points)
        if fill:
            self.draw.polygon(pts, fill=(*_color(fill), 255))
        if outline:
            self.create_line(*[(x / SS, y / SS) for x, y in pts + pts[:1]],
                             fill=outline, width=width, joinstyle='round')

    def create_text(self, x, y, text='', fill='black', font=None, anchor='center', **_):
        self.texts.append((x, y, text, fill, font, anchor))

    def photo(self, master=None):
        img = self.image.reduce(SS)
        if self.texts:
            draw = ImageDraw.Draw(img)
            anchors = {'center': 'mm', 'w': 'lm', 'e': 'rm', 'n': 'mt', 's': 'mb'}
            for x, y, text, fill, font, anchor in self.texts:
                family, size, *style = font if font else ('Segoe UI', 9)
                px = abs(size) * 96 / 72 if size > 0 else abs(size)
                draw.text((x, y), str(text), fill=(*_color(fill), 255),
                          font=_font(px, family, 'bold' in style),
                          anchor=anchors.get(anchor, 'mm'))
        return ImageTk.PhotoImage(img, master=master)

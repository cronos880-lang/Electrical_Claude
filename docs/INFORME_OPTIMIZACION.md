# Electrical Work Compacto V0.5.4 OPT — Informe de optimización

**Estado:** versión EXPERIMENTAL para pruebas. No sustituye a la V0.5.3 hasta su aprobación.
**Base:** Compacto V0.5.3 (rama `desarrollo-compacto` de Electrical-Work, idéntica al ZIP
`V0_5_3_COMPLETA_PRUEBA`). Copia intacta conservada en este repositorio con la etiqueta `base-v0.5.3`.

## 1. Auditoría (Fase 1)

**Arquitectura.** Python 3.9+ con Tkinter. Sin dependencias obligatorias; Pillow opcional para el
suavizado. Arranque mediante `INICIAR_WINDOWS.bat`. Proyectos `.ework` en JSON.

| Archivo | Función |
|---|---|
| `electrical_work.py` | Interfaz, eventos de ratón/teclado y motor de dibujo en pantalla |
| `core.py` | Modelo, geometría (bornes, cables, uniones), guardado y SVG |
| `symbology.py` | Primitivas vectoriales de los símbolos |
| `quality_render.py` | Rasterizado suavizado con Pillow (pantalla) |
| `page_layout.py`, `pdf_export.py`, `documentation.py` | Hoja, cajetín, PDF y documentación |

**Sistema de dibujo (V0.5.3).** Cada cambio llamaba a `redraw()`, que borraba el lienzo entero
(`delete('all')`) y lo recreaba: papel, rejilla, marco, cajetín, cables, símbolos y etiquetas. Los
símbolos y etiquetas se rasterizaban con Pillow a 4× y se guardaban en una caché.

**Causas medidas de la lentitud** (perfilador `cProfile` sobre un esquema de 154 símbolos):

1. **La caché de imágenes no funcionaba en esquemas medianos/grandes.** Tenía 220 entradas y un
   esquema de 154 símbolos necesita 462 (símbolo + etiqueta). Con LRU se vaciaba en cada
   redibujado: **todo se volvía a rasterizar siempre** (≈ 70 % del tiempo).
2. **La clave de la caché incluía la posición absoluta.** Al mover un símbolo un paso de rejilla su
   imagen dejaba de servir: arrastrar = rasterizar de nuevo en cada movimiento del ratón.
3. **Cada etiqueta volvía a cargar su fuente desde disco** (`ImageFont.truetype`, con búsqueda en
   la carpeta de fuentes): ≈ 35 % del tiempo de rasterizado.
4. **Redibujado completo en cada evento de arrastre**, aunque solo se mueva un objeto.
5. **Rejilla de hasta 11 600 puntos** (zoom ≥ 145 %) recreados en cada redibujado, la mayoría
   fuera de la pantalla.
6. Imágenes insertadas decodificadas y reescaladas (LANCZOS) en cada redibujado.
7. `junction_points` comparaba cada extremo con todos los cables (cuadrático).

**Limitaciones gráficas encontradas.**

- Cables dibujados por Tk (sin suavizado, grosor fraccionario redondeado por el sistema) y
  símbolos dibujados por Pillow (suavizados, otro grosor): **en las uniones cable‑borne había
  cambios de grosor y pequeños huecos** (visible en `comparativa_grafica_V0_5_4_OPT.png`).
- Grosores distintos según el elemento (cables 1,65; símbolos 1,55; marco 1,4) y coordenadas en
  medio píxel: líneas horizontales/verticales borrosas (dos píxeles grises en vez de uno nítido).
- Texto rasterizado a 4× y reducido con LANCZOS: letras algo difusas y con halo.
- Puntos de unión sin suavizado.

## 2. Plan aplicado (Fase 2) y cambios (Fase 3)

| # | Problema | Solución | Beneficio | Riesgo de regresión | Archivos |
|---|---|---|---|---|---|
| 1 | Caché saturada | LRU limitada por píxeles (≈ 24 Mpx) | Sin rasterizados repetidos | Más memoria (+40 MB máx.) | `electrical_work.py` |
| 2 | Caché dependiente de posición | Clave = geometría relativa + fracción de píxel del origen | Mover no rasteriza | Ninguno: misma imagen | `quality_render.py`, `electrical_work.py` |
| 3 | Fuentes recargadas | Fuentes resueltas una vez y en memoria | ×3 en etiquetas | Ninguno | `quality_render.py` |
| 4 | Redibujado total al arrastrar | Redibujado parcial (objetos movidos + cables cuya geometría cambia + uniones); al soltar, redibujado completo como antes | Arrastre ×18–×238 | Orden de apilado provisional durante el arrastre | `electrical_work.py` |
| 5 | Capa fija recreada | Capa estática (papel, rejilla, marco, cajetín) solo al cambiar zoom, tamaño, título u hojas | Clic y selección ×19–×52 | Ninguno detectado | `electrical_work.py` |
| 6 | Rejilla completa | Solo zona visible + margen; se completa al desplazar; creación en bloque | Zoom alto fluido | Ninguno: mismos puntos | `electrical_work.py` |
| 7 | Zoom lento | Zoom progresivo: trazo vectorial inmediato y afinado por tandas al parar | Zoom ×6–×18 | Durante ~0,2 s se ven trazos sin suavizar | `electrical_work.py` |
| 8 | Imágenes reprocesadas | Caché de imágenes escaladas | Arrastre con imágenes fluido | Ninguno | `electrical_work.py` |
| 9 | Uniones cuadráticas | Prefiltro por caja envolvente (resultado idéntico, probado) | Menos CPU | Ninguno | `core.py` |
| 10 | Geometría compacta recalculada | Memoria de la geometría relativa de cada símbolo | Arrastre de grupos | Ninguno (PDF/SVG no la usan) | `electrical_work.py` |
| 11 | Líneas borrosas / grosores distintos | Grosor entero único (cables, símbolos, uniones) alineado a la rejilla de píxeles; tramos ortogonales con cobertura exacta | Líneas nítidas, uniones continuas | Por debajo de ~94 % de zoom efectivo el trazo es de 1 px | `quality_render.py`, `electrical_work.py` |
| 12 | Texto difuso | Texto a resolución final con suavizado FreeType | Etiquetas más nítidas | Ninguno | `quality_render.py` |
| 13 | Halos del reescalado | Sobremuestreo 4× con promedio exacto (`reduce`) en vez de LANCZOS | Curvas limpias sin halo | Ninguno | `quality_render.py` |
| 14 | Enmarcar dos veces seguidas fallaba | La segunda pulsación rápida (que Tk trata como doble clic) inicia otro recuadro | Lo exigía la prueba existente `test_enmarcar_gui` | Ninguno | `electrical_work.py` |

**No se ha cambiado**: interfaz, colores, textos (salvo el número de versión), herramientas,
atajos, dimensiones de los símbolos, coordenadas, bornes, formato `.ework`, PDF, SVG,
documentación ni el lanzador `INICIAR_WINDOWS.bat`.

## 3. Pruebas comparativas (Fase 4)

Mismo equipo, mismo intérprete (Python 3.12.11, Tk 8.6, Pillow 12.3.0), mismos esquemas
sintéticos (sin datos del usuario) y eventos de ratón reales de Tk. Tiempos hasta la pantalla
actualizada. Se reproducen con `MEDIR_RENDIMIENTO.bat` o `python tests/bench_rendimiento.py`.
Datos brutos en `docs/mediciones/`.

**Esquema mediano (60 símbolos, 59 cables) · zoom 100 %**

| Operación (mediana) | V0.5.3 | V0.5.4 OPT | Mejora |
|---|---:|---:|---:|
| Redibujado completo | 40.9 ms | 11.4 ms | ×4 |
| Clic para seleccionar | 40.4 ms | 11.6 ms | ×3 |
| Arrastrar un símbolo (por paso) | 45.6 ms | 3.0 ms | ×15 |
| Arrastrar grupo (por paso) | 68.8 ms | 17.5 ms | ×4 |
| Enmarcar (por paso) | 0.4 ms | 0.5 ms | ≈ |
| Zoom con la rueda (por paso) | 430.3 ms | 71.4 ms | ×6 |
| Ratón con herramienta Cable | 0.6 ms | 0.6 ms | ≈ |

**Esquema grande (154 símbolos, 153 cables) · zoom 100 %**

| Operación (mediana) | V0.5.3 | V0.5.4 OPT | Mejora |
|---|---:|---:|---:|
| Redibujado completo | 540.4 ms | 26.4 ms | ×20 |
| Clic para seleccionar | 539.5 ms | 28.0 ms | ×19 |
| Arrastrar un símbolo (por paso) | 542.4 ms | 4.8 ms | ×112 |
| Arrastrar grupo (por paso) | 530.7 ms | 30.0 ms | ×18 |
| Enmarcar (por paso) | 0.7 ms | 0.8 ms | ≈ |
| Zoom con la rueda (por paso) | 1058.6 ms | 112.1 ms | ×9 |
| Ratón con herramienta Cable | 1.2 ms | 1.1 ms | ≈ |

**Esquema grande (154 símbolos, 153 cables) · zoom 250 %**

| Operación (mediana) | V0.5.3 | V0.5.4 OPT | Mejora |
|---|---:|---:|---:|
| Redibujado completo | 1130.2 ms | 20.5 ms | ×55 |
| Clic para seleccionar | 1161.8 ms | 22.3 ms | ×52 |
| Arrastrar un símbolo (por paso) | 1152.6 ms | 4.8 ms | ×238 |
| Arrastrar grupo (por paso) | 1129.4 ms | 36.9 ms | ×31 |
| Enmarcar (por paso) | 2.0 ms | 1.1 ms | ×2 |
| Zoom con la rueda (por paso) | 1229.1 ms | 68.3 ms | ×18 |
| Ratón con herramienta Cable | 1.6 ms | 1.3 ms | ≈ |

| Otros | V0.5.3 | V0.5.4 OPT |
|---|---:|---:|
| Arranque de la ventana | 301 ms | 305 ms |
| Guardar / abrir proyecto grande | 6,1 / 2,4 ms | 5,7 / 2,7 ms |
| Memoria máxima del proceso | 71 MB | 112 MB (caché de imágenes, limitada) |

Referencia: 16 ms por paso equivalen a 60 imágenes por segundo. En la V0.5.3 arrastrar en un
esquema grande daba ≈ 2 imágenes por segundo; en la V0.5.4 OPT, más de 30 (grupos) y más de
200 (un símbolo).

**Regresión funcional** (`python -m unittest discover -s tests -v`, 17 pruebas, todas correctas):
- Geometría de los 62 símbolos × 4 giros compatible con bornes y rejilla (prueba existente).
- Guardado/apertura y exportación SVG/PDF (pruebas existentes + archivo idéntico al reguardar).
- Puntos de unión: el algoritmo acelerado da el mismo resultado que el original en 60 esquemas
  aleatorios.
- Arrastre de símbolo y de grupo: el redibujado parcial deja exactamente las mismas cajas y
  puntos de unión que un redibujado completo.
- Zoom progresivo: tras el afinado, el dibujo es idéntico al redibujado completo.
- Deshacer tras arrastrar restaura las posiciones.
- Enmarcar (3 pruebas existentes, ahora todas correctas).
- Interfaz: captura de la ventana completa comparada píxel a píxel con la V0.5.3: cabecera,
  barras y herramientas idénticas; solo cambia el texto de versión.

**Límites de estas pruebas.** Se han hecho en Linux con pantalla virtual. Las cifras absolutas
en Windows serán distintas (las proporciones deberían mantenerse). Falta la prueba real en
Windows, impresión y proyectos reales del usuario.

## 4. Revisión 2: manejo del ratón (pedido por el usuario)

| Acción | V0.5.3 | V0.5.4 OPT (rev. 2) |
|---|---|---|
| Puntero, izquierdo sobre objeto | Seleccionar y mover | Igual |
| Puntero, izquierdo en vacío + arrastrar | Desplazar la hoja | Marcar recuadro de selección |
| Derecho + arrastrar | — | Desplazar la hoja (con zoom, cualquier herramienta) |
| Derecho (clic) con objetos marcados | Menú de etiqueta | Borrar lo marcado (Ctrl+Z deshace) |
| Derecho (clic) sin selección | Menú de etiqueta / cancelar trazo | Igual |
| «Enmarcar» en el desplegable de Líneas | Sí | Retirado |

Pruebas: `tests/test_enmarcar_gui.py` reescrito para este comportamiento (9 pruebas: marcar,
cable cruzado, deseleccionar, mover grupo marcado, marcar con zoom sin desplazar, desplazar con
el derecho, borrar con el derecho y deshacer, no borrar sin selección, cancelar trazo).
Total: 23 pruebas correctas.

## 5. Revisión 3: nitidez y acabado

- **Modo DPI** (`dpi_ui.py`). Pantalla del usuario: 1920×1080 al 150 %. Sin el modo DPI, Windows
  dibujaba la ventana a 1280×720 y la ampliaba ×1,5 (imagen borrosa). Ahora el proceso se declara
  compatible con DPI antes de crear la ventana; las fuentes en puntos se adaptan solas y las medidas
  de interfaz en píxeles (márgenes, bordes, alturas, iconos) se multiplican por el factor de escala,
  de modo que la interfaz conserva su tamaño visual. Los textos del plano se fijan en píxeles para que
  no crezcan dos veces. Tolerancias del ratón escaladas. Desactivable con `SIN_DPI.txt`.
  Comparación simulada en `docs/vista_previa_modo_DPI.png`. 23 pruebas correctas a 96 y 144 ppp.
- Marco con zonas 1–8 (`page_layout.py`), compartido por pantalla, PDF y SVG.
- Iconos de herramientas suavizados (`quality_render.IconPainter`), también escalados en modo DPI.
- Cabecera y barra de edición en Segoe UI Semibold.

## 6. Propuestas NO implementadas (requieren autorización)

1. **Nitidez en pantallas con escalado de Windows (125 %, 150 %).** Python para Windows no se
   declara «DPI aware» y Windows amplía la ventana como imagen: todo (botones, textos y dibujo) se
   ve borroso. Activarlo (`SetProcessDpiAwareness`) daría nitidez total, pero cambia el tamaño en
   píxeles de botones y barras: hay que revisar la interfaz. Es probablemente **la mejora de
   nitidez más visible** si usas escalado.
2. **Grosor mínimo de 2 px** en zoom bajo (líneas más «gruesas» como en la V0.5.3) si el trazo de
   1 px te parece demasiado fino.
3. Rótulos del marco (A–H, 1–5) y textos del cajetín dibujados también con el motor suavizado.
4. Anillo de borne con el trazo centrado sobre el radio (como en el PDF): los anillos se verían
   ligeramente mayores en pantalla. Se ha mantenido el tamaño de la V0.5.3.

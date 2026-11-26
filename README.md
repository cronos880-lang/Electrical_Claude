# Electrical Work Compacto V0.5.5 — versión oficial

Editor de esquemas eléctricos para Windows (Python + Tkinter), parte de *Suite de Programas*.
Dibuja esquemas; no realiza simulación eléctrica ni certificación de seguridad.

**Estado:** V0.5.5 oficial, aprobada por el usuario el 26-11-2026.
**Paquete de instalación:** [`entregas/Electrical_Work_V0_5_5_Oficial.zip`](entregas/Electrical_Work_V0_5_5_Oficial.zip)

## Ejecutar en Windows

1. Descomprime el paquete en una carpeta nueva.
2. Requiere Python 3.9 o superior con Tkinter (instalación oficial de python.org). Pillow es recomendado
   (suavizado de dibujo); el lanzador ofrece instalarlo.
3. Ejecuta `INICIAR_WINDOWS.bat` (la Suite de Programas lanza este mismo archivo).
4. Para diagnosticar un fallo: `INICIAR_CON_CONSOLA.bat`.

## Contenido

| Archivo | Función |
|---|---|
| `electrical_work.py` | Interfaz, eventos y motor de dibujo en pantalla |
| `core.py` | Modelo, geometría, cables, guardado y SVG |
| `symbology.py` | Símbolos vectoriales |
| `quality_render.py` | Dibujo suavizado (Pillow), iconos |
| `dpi_ui.py` | Nitidez con escalado de Windows (modo DPI) |
| `documentation.py`, `page_layout.py`, `pdf_export.py` | Documentación, marco de hoja, PDF |
| `tests/` | Pruebas automáticas y banco de medidas (`python -m unittest discover -s tests`) |
| `LEEME_PRIMERO_V0_5_5.txt`, `CAMBIOS_V0_5_5.txt` | Instrucciones y cambios |
| `docs/INFORME_OPTIMIZACION.md` | Auditoría, plan, mediciones y decisiones |
| `docs/vistas_previas/` | Comparativas y vistas previas aprobadas |
| `docs/historial/` | Documentación de versiones anteriores |
| `docs/SIGUIENTE_TAREA_PORTADA_PDF.md` | Notas para la próxima tarea |

## Versiones

- `v0.5.5-oficial` (etiqueta): esta versión.
- `base-v0.5.3` (etiqueta): copia intacta de la V0.5.3 sobre la que se trabajó.
- El repositorio original `Electrical-Work` no se ha modificado.

## Protección de datos

El repositorio no incluye proyectos de usuario ni datos personales. Los `.ework`, PDF y copias de
seguridad están excluidos por `.gitignore`; aun así, revisa siempre la lista antes de subir algo a mano.

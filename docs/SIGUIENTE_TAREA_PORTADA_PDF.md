# Siguiente tarea: portada del PDF

Petición del usuario (26-11-2026): poder crear una **portada (tapa) para el PDF** exportado, con
logotipo, título y algún elemento gráfico vectorial. Pendiente de definir el diseño con vistas previas
antes de implementar, como en las revisiones anteriores.

## Dónde encaja en el código

- `pdf_export.py`
  - `PDFPage`: primitivas ya disponibles — `line`, `rect` (con relleno), `text` (fuente, tamaño,
    negrita, alineación) e `image` (imágenes incrustadas, útil para el logotipo).
  - `_sheet_page(...)` dibuja cada hoja; `_table_pages(...)` la documentación.
  - `export_project_pdf(project, path, sheet_indices, include_documentation, documentation_only)`:
    aquí se añadiría la página de portada al principio (opción nueva `include_cover`).
- `electrical_work.py` → `export_pdf_dialog()`: añadir la casilla «Añadir portada» y, si procede,
  un diálogo de datos de portada.
- `core.py` → `validate_project`: los datos de portada (título, cliente, autor, fecha, logotipo en
  base64) pueden guardarse en el proyecto como campo opcional, igual que la nomenclatura del PLC,
  para no romper la compatibilidad con versiones anteriores.

## Ideas a proponer (con vista previa)

- Composición A4 apaisado coherente con el marco del plano (verde `#299144`, azul tinta `#21364c`).
- Logotipo cargado por el usuario (PNG/JPG), escalado sin deformar.
- Bloque de título: proyecto, descripción, cliente, autor, fecha, revisión, número de hojas.
- Elemento vectorial decorativo dibujado con primitivas del PDF (por ejemplo, un trazo de
  esquema unifilar estilizado o una retícula técnica), sin imágenes externas.
- Índice automático de hojas (número y título) opcional en la propia portada.

## Normas a mantener

Versión experimental separada hasta aprobación, compatibilidad de `.ework`, sin datos personales en
el repositorio, entregas con solo archivos modificados cuando sea posible.

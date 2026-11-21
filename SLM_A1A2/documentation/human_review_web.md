# Interfaz local para la revisión humana v2

Implementación del 11 de octubre de 2026, como continuación de las fichas preparadas para el trabajo de titulación. El docente todavía debe coordinarse. La aplicación se entrega con cero notas humanas; las comprobaciones usan fixtures sintéticas y no se importan a los resultados experimentales.

## Qué se hizo y por qué

Se creó `review_web/revision_humana.html`, un instrumento portátil para leer las 180 respuestas del paquete ciego ya fijado, aplicar los siete criterios 0/1/2/NA, registrar los dos juicios semánticos, el veredicto y su fundamento, guardar borradores y exportar evaluaciones. Incluye la asignación preestablecida de 45 respuestas para segunda revisión. Las notas permanecen por evaluador; la aplicación no adjudica desacuerdos, invalida casos ni cambia puntajes automáticos.

El HTML es autónomo, sin dependencias externas, CDN, servicios, cuentas o servidor obligatorio. Su política de contenido bloquea conexiones de red y envío de formularios. Las respuestas se muestran con `textContent`, nunca como HTML ejecutable. Un JSON defectuoso se mantiene visible y no determina automáticamente si la respuesta es evaluable. Esto reduce la instalación requerida al docente y conserva el texto exacto que se debe valorar.

## Datos, ciego y persistencia

El constructor solo incorpora `reviewer_materials/blind_packet.json` y los IDs del plan público de segunda revisión. No lee el crosswalk coordinador. Rechaza campos extra, IDs repetidos, asignaciones ajenas al paquete y plantillas con juicios prellenados. El texto fuente exacto del packet queda incrustado y se verifica con SHA-256 antes de habilitar la revisión. El registro `.build.json` guarda hashes de las fuentes de la interfaz, del paquete y del HTML generado; repetir el constructor con los mismos bytes produce el mismo artefacto.

La elección del evaluador sobre si el texto original contiene errores es auxiliar: guía qué criterios no aplican, pero se guarda en metadatos separados. No se revela la condición del gold. Ante un desacuerdo con la condición de referencia, el coordinador recibe un error explícito y debe revisar el caso; no se reescribe el juicio ni se fuerza la nota para que pase la validación.

El progreso se conserva en `localStorage`, separado por SHA del paquete, con avisos si falla. La continuidad entre ubicaciones, equipos o perfiles se hace mediante respaldo JSON, que incluye borradores y completadas. Restaurar valida versión, paquete, IDs, tipos y notas completadas antes de sustituir el estado. Cada ficha guarda su identificador de evaluador y su fecha; cambiar los datos de sesión no reetiqueta evaluaciones anteriores. Los evaluadores deben trabajar en sesiones separadas. No hay autenticación, firma digital ni evidencia automática de cualificación docente: el investigador coordina y verifica la identidad del evaluador.

## Exportación e integración

Solo se exportan fichas que el usuario haya completado explícitamente y que pasen la validación. Modificarlas las devuelve a borrador. El JSONL lleva `blind_output_id` y los campos exactos del contrato `human_review_v2/1.0`; no incluye identidades privadas, condición, gold ni juicios auxiliares. El JSON de metadatos registra SHA-256 de los bytes UTF-8 exactos del JSONL (con salto de línea final), tamaño, cantidad, fecha UTC y los juicios auxiliares por ID ciego. La exportación parcial está permitida y se informa su cantidad; no implica que se haya terminado toda la muestra.

El coordinador debe conservar juntos JSONL, metadatos y cualquier respaldo recibido. Desde `SLM_A1A2`, valida antes de importar:

```powershell
.\.venv\Scripts\python.exe scripts/validate_human_review_web_export.py --reviews RUTA_NOTAS.jsonl --metadata RUTA_METADATOS.json --crosswalk analysis_v2/human_review_development60/coordinator_only/identity_crosswalk.json
```

El validador es de solo lectura. Comprueba hashes, cobertura exacta de IDs en metadatos, ciego, el crosswalk verificado, identidades vinculadas a las filas v2 y anclas contra la condición de referencia. Rechaza discrepancias con el juicio auxiliar del evaluador y no modifica archivos. Cuando termine sin errores, importa con un nombre nuevo:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_human_review_v2.py import --scope results_120 --reviews RUTA_NOTAS.jsonl --output-name docente_01_entrega_01 --crosswalk analysis_v2/human_review_development60/coordinator_only/identity_crosswalk.json
```

El importador preservado crea una capa humana independiente y rechaza sobrescrituras y duplicados dentro de la entrega. Entregas sucesivas pueden contener las mismas fichas: deben conservarse como versiones y seleccionarse de forma trazada, sin sumar duplicados ni escoger por calidad. El segundo evaluador usa otro identificador y la asignación fija de 45. El acuerdo y la adjudicación siguen pendientes hasta contar con juicios reales.

## Reproducción

```powershell
.\SLM_A1A2\.venv\Scripts\python.exe SLM_A1A2/scripts/build_human_review_web.py
node SLM_A1A2/review_web/test_review_core.cjs
.\SLM_A1A2\.venv\Scripts\python.exe -m unittest discover -s SLM_A1A2/scripts -p "test_*.py" -v
```

Las fuentes mantenibles son `review_web/src/page.html`, `style.css`, `review_core.js` y `app.js`. El HTML generado es el archivo que se distribuye. No se debe entregar `coordinator_only` ni hospedar esa carpeta. Para usarlo no hace falta publicar un sitio.

La vista previa de esta sesión está en `http://127.0.0.1:8120/revision_humana.html`, con un servidor temporal vinculado solo a loopback y sin arranque automático. Si se cierra y se desea volver a usar esa vista, desde la raíz del proyecto se puede iniciar el siguiente comando y detenerlo con Ctrl+C:

```powershell
.\SLM_A1A2\.venv\Scripts\python.exe -m http.server 8120 --bind 127.0.0.1 --directory SLM_A1A2/review_web
```

## Verificación y límites

Los resultados de las pruebas y la revisión visual se registran en `review_web/verification_20261011.json`. Pasaron 196 pruebas de Python y la suite Node del núcleo web; una prueba compara 236 variantes sintéticas del contrato entre JavaScript y el validador Python. Incluyen integridad del paquete incrustado, protección ante contenido HTML de las respuestas, validación de anclas/fechas/tipos, rechazo de notas incompletas y archivos alterados, exportación compatible y recuperación de progreso. La prueba del navegador usa un paquete sintético separado para no añadir notas de prueba a las 180 fichas. Se verificaron ambos JSONL descargados (caso con errores y control) contra el contrato Python, y SHA/tamaño/cantidad contra sus metadatos. Las 180 fichas reales siguen sin notas completadas.

El cierre comprobó los 93 archivos originales contra el commit de referencia, los hashes vigentes de 164 fuentes y 76 artefactos v2, y la integridad de los 24 artefactos de Fase 1. Ninguno cambió. Se conserva una captura de la interfaz en `review_web/preview_20261011.jpg`; las descargas y fichas sintéticas de QA quedan en `logs/review_web_qa/`, fuera de Git y de la importación humana.

La prueba inicial mostró que el navegador podía bloquear la segunda descarga automática. Se reemplazó por dos enlaces explícitos, cada uno activado por el usuario, y se verificaron ambos archivos descargados. Esto evita depender de permisos para descargas múltiples. La vista previa de Codex restringe URLs `file:`; la comprobación visual se hizo con HTTP en loopback, sirviendo únicamente la carpeta pública de la interfaz y otra carpeta sintética. Abrir el HTML directamente en el navegador de escritorio queda como comprobación manual del docente; el artefacto no usa fetch ni necesita servidor.

No se ejecutaron nuevas inferencias ni se accedió al test final. Las fuentes, métricas y respuestas históricas y v2 permanecen intactas. La revisión real está pendiente de coordinación humana. El guardado local puede limitarse en modo privado; por eso el respaldo y la entrega de ambos archivos son parte del procedimiento.

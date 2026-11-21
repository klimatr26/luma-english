# Protocolo de evaluación v2 — respuestas ya recogidas

Versión: `evaluation-v2.0`. Preparado el 11 de octubre de 2026 después de observar las respuestas y el diagnóstico de granularidad. **Análisis post hoc**, no métrica prerregistrada de las inferencias originales. La autorización del investigador es «Continúa haciendo eso», referida a evaluación versionada, pruebas, rúbrica/fichas humanas y reprocesamiento de RAW existentes.

## Alcance y conservación

Únicamente `results_120` (120×16) y `results_40_current_16` (40×16), ligados a sus hashes originales por el inventario y la selección de intentos del evaluador congelado. Salidas nuevas exclusivamente en `analysis_v2/`. Ninguna inferencia, ajuste de generación, descarga de pesos del benchmark, modificación de fuentes/results originales ni lectura del test final. Se instala ERRANT y su analizador lingüístico en un entorno independiente; procesar textos para medir ediciones no genera nuevas respuestas de los SLM evaluados.

El código primario sigue intacto. V2 reutiliza su validación de identidad/RAW y su parser para mantener comparabilidad de formato, pero **no** su regla de coincidencia literal de declaraciones para medir corrección del texto. Se conservan hashes de entradas, dependencias, código y este protocolo. Antes y después del procesamiento se cotejan las entradas: una variación aborta el cierre.

## Dimensiones separadas

1. **Ediciones del texto corregido:** ERRANT real sobre fuente→referencia y fuente→salida. Comparación exacta de posición de tokens fuente y texto corregido de cada edición; tipo ERRANT descriptivo, fuera de la clave de correspondencia. P/R/F0.5 micro sobre textos incorrectos con texto corregido observable. El número de ediciones ERRANT puede diferir de las 150 anotaciones intencionales, por segmentación y agrupación; se publica su denominador propio.
2. **Referencia primaria y alternativas completas:** publicar ambas mediciones. Solo se admiten `gold.corrected_text` y las alternativas completas congeladas. No combinar alternativas individuales para inventar referencias. Para el resultado multirreferencia se elige por caso el mayor F0.5, desempate determinista del componente; todos los scores por referencia y su índice quedan trazados. Esta selección de referencia válida no selecciona una respuesta o tentativa del modelo. No implica adjudicar variantes no listadas ni validar significado.
3. **Declaraciones:** reconstrucción literal cuando cada fragmento aparece una sola vez y no se solapa. Se compara el texto reconstruido con `corrected_text`; la coherencia acepta fragmentos cortos, largos o varias reparaciones agrupadas cuando realizan el mismo efecto. Fragmentos ausentes, ambiguos, no-op o solapados quedan explícitos. No se adivinan posiciones ni se certifica una declaración por hallar su corrección en otra parte del texto. Esta prueba no evalúa la verdad de la explicación ni su categoría.
4. **Controles:** modificación observada (CTMR), falsa alarma declarada (CFAR), preservación completa y flag correcto por separado. Desconocidos se publican como desconocidos, no como cero. `FCR` lingüístico de modificación innecesaria exige adjudicación humana; CTMR es su indicador mecánico.
5. **Formato:** JSON directo, recuperable, no recuperable y validez de esquema se mantienen separados. Se puede medir un `corrected_text` observable aunque el resto del esquema sea inválido; esa calidad textual no convierte la salida en usable ni en esquema válido. Texto inexistente, de tipo incorrecto o vacío queda no observable.
6. **Calidad pedagógica/humana:** instrumento separado de siete notas 0–2/NA, juicios explícitos de significado y explicación, identidad completa de respuesta y revisor. No se generan notas humanas, veredictos humanos ni confirmaciones a partir de métricas automáticas. Una ficha incompleta se rechaza; un veredicto de invalidación no excluye por sí solo un caso para un modelo.

## Denominadores y fallos

F0.5 textual principal v2 es **condicional a texto observable**, acompañado siempre del número de textos observables/esperados y problemas de esquema. No se sustituye silenciosamente una salida ausente por el original ni por una cadena vacía.

Se publica además `recall_all_primary_gold_unobservable_as_missed`: TP de referencia primaria en textos observables dividido por todas las ediciones gold primarias esperadas en incorrectos. Las no observables cuentan como omisiones por convención explícita. No es una estimación de FP de textos inexistentes ni convierte el F0.5 condicional en una medida completa del servicio. Los casos correctamente preservados y el formato constituyen dimensiones adicionales indispensables para selección.

Correspondencia exacta de texto se registra sin atribuir toda discrepancia a una corrección falsa. Las alternativas no listadas, cambios estilísticos y explicaciones quedan para revisión. Tampoco se asigna un nuevo C/P/I automático global que mezcle formato, edición y juicio pedagógico.

Convenciones matemáticas: P=1 si no hay ninguna edición predicha; R=1 si no hay ediciones gold; F0.5=0 cuando su denominador es cero. Un modelo sin correcciones frente a errores tiene R=0 y F0.5=0 aunque P=1 por convención. Si no hay textos observables, los agregados condicionales son `null`. Matching y métricas ERRANT conservan cambios de espacio observados por su tokenizador; no hay normalización silenciosa. CTMR y exact match v2 usan la cadena literal, incluidos espacios, mientras la interpretación lingüística de una modificación se reserva a revisión humana.

## Pruebas y selección

Pruebas sintéticas de equivalencia de fragmentos, cambios adicionales, inserción/borrado, contracciones, mayúsculas, puntuación, tokens repetidos, solapamientos, alternativas completas y entradas inválidas. Pruebas de contrato humano con identidad equivocada, campos omitidos, bool como nota, NaN/claves duplicadas y duplicación de registros. Pruebas de integración real ERRANT en el entorno independiente; sin inferencia del benchmark.

Después de procesar uniformemente todas las configuraciones se propondrán hasta tres candidatos, considerando calidad textual, cobertura, controles, formato y recursos. La propuesta seguirá siendo provisional hasta revisión humana pareada. Ni igualdad al gold ni F0.5 autoriza llamar fiable al feedback completo.

Se prepara un plan fijo de 60 casos de desarrollo para revisión: 30 controles y 30 incorrectos (15 A1/15 A2), estratificados por cantidad de errores y alternativas. Los mismos IDs se usan entre candidatos; semilla de muestreo 20261011. Fichas sin scores/modelo visibles, crosswalk aparte y notas sin rellenar. La selección de casos no depende de calidad de salidas. Una cola de anomalías es complemento, no sustituto de la muestra.

Lo observado en los 40 sigue siendo exploratorio, separado de los 120; no se suma como test independiente. El seguimiento de prompting, robustez y test final requiere un protocolo prospectivo y su etapa de ejecución correspondiente.

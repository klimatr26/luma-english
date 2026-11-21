# Seguimiento de la revisión y propuesta de prompts — 9 de noviembre de 2026

## Qué se recibió y qué queda pendiente

Se leyó el respaldo `respaldo_revision_2026-11-09T01-08-40-788Z.json`, sin editarlo. Contiene 180 fichas completadas por `kevin-01`: los mismos 60 casos de desarrollo en Qwen3.5-4B Q4_K_M, MiniCPM5-2B Q4_K_M y Gemma E2B UD-Q4_K_XL. Su SHA-256 es `91a638c9725894144a0b1307af9441c9eca2e40b6423263ab71a454e2b4dd24e`. Los IDs, contexto y hashes de respuesta se vincularon al paquete ciego y a las filas de evaluación v2.

Hay seis fichas con discrepancia entre `original_has_errors`, la condición de referencia y las anclas NA; además hay tres propuestas `INVALID_CASE`, una de ellas entre esas seis. Se proporcionaron [ocho fichas completas](human_review_cases_pending_20261109.md) para que el investigador pueda aclarar la intención con los textos a la vista. No se corrigieron notas ni se importó una capa humana definitiva. La selección expresa del usuario fue revisar estas discrepancias antes del cierre.

Los [resultados provisionales](human_review_results_20261109.md) publican tanto los valores tal como se introdujeron como una comparación entre los mismos 53 casos sin pendientes. MiniCPM conserva una ficha marcada no evaluable y su ausencia de notas numéricas. No se recalifica automáticamente esa ficha aunque el comentario contenga contenido analizable. La media /100 expresa puntos de rúbrica, no exactitud de clasificación. La muestra y los tres modelos no constituyen 180 casos independientes.

Las fichas declaran `2026-10-19`; esa fecha se conserva. La recepción y el análisis son del 9 de noviembre. No se atribuye la revisión a un docente externo ni se calcula acuerdo interevaluador: es revisión del investigador.

## Cómo se tradujeron las observaciones a instrucciones

Se creó un perfil **prospectivo y sin validación empírica**, `human-review-20261109`. El prompt base permanece literalmente intacto; se le anexan reglas comunes y un apéndice por familia. El registro de configuración está en [`demo/prompts/human_review_20261109.json`](../demo/prompts/human_review_20261109.json). No se insertan textos, referencias, respuestas esperadas ni soluciones particulares de los casos revisados.

| Observación trazable | Cambio propuesto | Límite |
|---|---|---|
| MiniCPM A1-C006: habla del estudiante al evaluador; otros comentarios de MiniCPM señalan el mismo tono | Dirigirse al aprendiz con `you/your`, sin describirle su texto a un grader | Se modifica el destinatario de la explicación, no su gramática ni la nota antigua |
| Gemma A2-C001/C003: comentario `for an A2 level` percibido como repetición de instrucciones | Lenguaje accesible al nivel sin repetir la etiqueta CEFR en el feedback | No se prohíbe el nivel como entrada: sigue guiando la accesibilidad |
| Gemma A2-C013 y notas de cercas Markdown | Objeto JSON sin cercas; `errors: []` cuando no hay errores; sin objetos vacíos ni ediciones duplicadas | El parser sigue distinguiendo JSON estricto de recuperado |
| Qwen A2-C013: `errors` y explicación declaran un cambio que no aparece en `corrected_text` | Verificación de coherencia entre fragmentos, ediciones, texto final y booleano | La instrucción no garantiza que el modelo cumpla; falta medirlo |
| Qwen A2-C008/C010 y aclaración del usuario sobre expresiones válidas poco comunes | Separar error real de recomendación opcional de escritura | No se convierte una sugerencia estilística en error ni se acepta un consejo lingüísticamente falso |
| Observaciones sobre variantes regionales y correcciones excesivas | Admitir variantes estándar y lecturas gramaticales plausibles; no asumir contexto físico no dado | No se modifica el gold ni se resuelve retrospectivamente una disputa editorial |
| Explicaciones vagas o que hablan de otras oraciones sin respaldo | Regla breve y específica del cambio real, sin afirmaciones sobre ediciones inexistentes | La corrección de una explicación sigue requiriendo juicio humano |

Se reforzó en MiniCPM la coherencia de `is_correct` con el original y las ediciones; en Qwen la validez y especificidad de la explicación; en Gemma el JSON desnudo y la ausencia de duplicados/objetos vacíos. Son hipótesis derivadas de desarrollo, no evidencia de una mejora.

## Recomendaciones opcionales y contrato JSON

El usuario aclaró que una expresión válida pero poco común puede recibir una recomendación de buena escritura sin tener que considerarse incorrecta. Se mantienen los cuatro campos del contrato para separar ambas cosas:

- Si el original no tiene errores reales: `is_correct=true`, `corrected_text` idéntico y `errors=[]`.
- Si existe una sugerencia útil y válida: puede ir en `feedback`, marcada como `Optional writing suggestion (not an error): ...`. No activa una corrección ni cambia el booleano.
- No es obligatorio sugerir algo. En un original correcto, un reconocimiento breve o feedback vacío siguen permitidos, de acuerdo con los comentarios del investigador.
- Si hay errores reales: estos sí se corrigen y explican en los campos existentes. No se mezcla el consejo opcional con la lista de errores.

Esta política es una versión de producto posterior a las observaciones. El prompt anterior exigía correcciones mínimas y no reescritura estilística. No se reinterpreta su resultado a posteriori como si hubiera recibido las nuevas instrucciones. Una preferencia aceptable como sugerencia no justifica que el modelo afirmara incorrectamente que el original tenía un error; tampoco vuelve correcto un consejo erróneo.

La rúbrica humana congelada no se ha alterado. Si se decide evaluar sistemáticamente la utilidad de consejos opcionales, debe definirse una dimensión separada o una nueva versión de rúbrica antes de producir sus resultados. No se añade un criterio a las siete notas históricas ni se imputan nuevas notas a partir de comentarios.

## Integración en el prototipo

La versión compilada está en `demo/publish/review_20261109/WritingDemo.WinForms.exe`, separada del ejecutable anterior. El selector **Modo de retroalimentación** ofrece `Base experimental` y `Revisión humana · pendiente de validar` para las tres familias revisadas; la interfaz selecciona el perfil revisado al elegirlas. En LFM se conserva únicamente el perfil base porque este respaldo no contiene revisiones LFM. Aplicar el apéndice de una familia a sus otras cuantizaciones es una hipótesis sin validación, no una conclusión obtenida de sus notas Q4.

`LlamaRuntime.GenerateAsync` conserva por defecto el perfil base para los clientes anteriores y el harness de demostración. La interfaz pasa el perfil elegido explícitamente. Las nuevas sesiones (`writing_local_demo/1.1`) guardan ID y SHA-256 del prompt realmente usado, junto al estado de validación. `EvidenceSha256` del catálogo queda vacío para no atribuir evidencia empírica al perfil nuevo; el SHA del respaldo que motivó la propuesta se registra por separado en el JSON de configuración.

No cambian pesos, plantillas nativas, thinking desactivado, contexto 4096, presupuesto 512, semilla ni sampling de cada familia. No se añadieron grammar, reintentos por calidad ni campos JSON nuevos. Cambiar de perfil limpia el resultado visible anterior. La adaptación de prompts no se ha aplicado al runner del benchmark, al manifiesto congelado ni a la página de revisión histórica.

## Verificación y siguiente experimento

Pasaron 203 pruebas Python, incluidas siete nuevas sobre cálculo de notas, NA, cobertura, identidad del paquete y tratamiento de pendientes. Pasaron las cuatro suites C# (parser, activos, runtime y perfiles de prompt) y la compilación Release sin advertencias; en la carpeta `demo`, el SDK seleccionado fue 10.0.403 conforme al `latestPatch` de `global.json`. Se inspeccionó visualmente el selector y la disponibilidad del prompt base. No se cargaron modelos ni se ejecutaron inferencias nuevas en esta entrega. El registro técnico y hashes están en `analysis_v2/human_review_20261109/verification.json`.

Para medir la propuesta falta fijar prospectivamente la comparación A/B, conservar el prompt anterior como control y usar los mismos modelos, textos, parámetros y reglas por tratamiento. Se deben reportar por separado errores reales, falsas alarmas en controles, coherencia del JSON, validez de la explicación y recomendaciones opcionales. Los casos utilizados para diseñar estos apéndices son desarrollo; no pueden convertirse en evidencia independiente de generalización. Las inferencias de comparación no se ejecutan por preparar este perfil y el test final continúa sin acceso.

Para Android/Vulkan se preparó una [evaluación de viabilidad separada](vulkan_android_feasibility_20261109.md); no se cambiaron los binarios CUDA del experimento.

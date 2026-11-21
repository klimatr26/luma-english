# Revisión humana aclarada — 9 de noviembre de 2026

**Estado: 180 fichas validadas e importadas, con ocho aclaraciones confirmadas por el investigador.** Este cierre corresponde a la revisión de desarrollo, no al test final.

Revisor: `kevin-01`. El respaldo original conserva SHA-256 `91a638c9725894144a0b1307af9441c9eca2e40b6423263ab71a454e2b4dd24e` y no se ha editado. Las fichas conservan fecha declarada `2026-10-19`; las aclaraciones tienen fecha `2026-11-09` en un registro separado. Sus comentarios originales también se conservan.

## Puntuaciones después de las aclaraciones

Para cada ficha se promedian sus criterios numéricos 0–2; NA se omite y no se transforma en cero. La media del modelo da igual peso a cada ficha con notas. Puntos /100 = media ×50: no es porcentaje de precisión ni F0.5.

| Configuración | Media /2 | Puntos /100 | Fichas con nota /60 | CORRECT | PARTIAL | INCORRECT |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-4B Q4_K_M | 1.8950 | 94.7500 | 60/60 | 52 | 6 | 2 |
| Gemma E2B UD-Q4_K_XL | 1.8450 | 92.2500 | 60/60 | 49 | 6 | 5 |
| MiniCPM5-2B Q4_K_M | 1.7497 | 87.4859 | 59/60 | 41 | 11 | 8 |

MiniCPM mantiene una ficha marcada no evaluable, con todas las notas NA y veredicto INCORRECT. No se inventa una nota para ella: la media es condicional a 59 fichas con nota. Los tres modelos conservan los mismos 60 casos; no quedan propuestas INVALID_CASE ni se excluye ningún caso.

## Notas por criterio

Se muestra media /2 y denominador numérico n. Las diferencias de denominador reflejan NA y la ficha no evaluable, no resultados omitidos sin declarar.

| Criterio | Qwen4B Q4 | Gemma UD-Q4 | MiniCPM Q4 |
|---|---:|---:|---:|
| `detection` | 1.9000 (n=30) | 1.7667 (n=30) | 1.4667 (n=30) |
| `correction` | 1.9000 (n=30) | 1.6667 (n=30) | 1.4000 (n=30) |
| `meaning_preservation` | 1.9667 (n=60) | 2.0000 (n=60) | 1.9492 (n=59) |
| `level_appropriateness` | 2.0000 (n=60) | 1.9500 (n=60) | 1.9492 (n=59) |
| `grammatical_explanation` | 1.8136 (n=59) | 1.7500 (n=60) | 1.4576 (n=59) |
| `pedagogical_clarity` | 1.9000 (n=60) | 1.8167 (n=60) | 1.7966 (n=59) |
| `clean_text_handling` | 1.7000 (n=30) | 1.8000 (n=30) | 1.9310 (n=29) |

## Cambios confirmados

Los ocho registros siguen siendo controles: detección/corrección se mantienen o pasan a NA y `original_has_errors=false`. Esto no cambia el gold. Las notas que no se enumeran a continuación permanecen intactas.

| Ficha | Aclaración aplicada |
|---|---|
| MiniCPM / A1-C006 | `original_has_errors`: `True` → `False`; `review.detection`: `2` → `NA`; `review.correction`: `2` → `NA`; `review.clean_text_handling`: `NA` → `2`. Es correcto; la observación sobre hablar al evaluador es una preferencia de destinatario, no un error del original. |
| Gemma / A2-C001 | `original_has_errors`: `True` → `False`; `review.detection`: `2` → `NA`; `review.correction`: `2` → `NA`; `review.clean_text_handling`: `NA` → `2`. Es correcto. Evitar mencionar el nivel innecesariamente es una preferencia; el investigador admite 2/true. |
| Gemma / A2-C003 | `original_has_errors`: `True` → `False`; `review.detection`: `2` → `NA`; `review.correction`: `2` → `NA`; `review.clean_text_handling`: `NA` → `2`. Similar a A2-C001: el comentario de nivel no obliga a penalizar la corrección. |
| Qwen / A2-C014 | `original_has_errors`: `True` → `False`; `review.detection`: `2` → `NA`; `review.correction`: `2` → `NA`; `review.clean_text_handling`: `NA` → `2`. El feedback vacío en un texto correcto es aceptable; el investigador mantiene la convención 2/true. |
| Gemma / A2-C013 | `original_has_errors`: `True` → `False`; `review.detection`: `0` → `NA`; `review.correction`: `0` → `NA`; `review.clean_text_handling`: `NA` → `2`; `review.grammatical_explanation`: `0` → `2`; `review.explanations_ok`: `False` → `True`; `review.verdict`: `INVALID_CASE` → `CORRECT`. Juicio lingüístico CORRECT confirmado. El objeto vacío de errors se registra como problema de formato/coherencia aparte. |
| Qwen / A2-C013 | `original_has_errors`: `True` → `False`; `review.detection`: `1` → `NA`; `review.correction`: `1` → `NA`; `review.clean_text_handling`: `NA` → `0`. Se mantiene INCORRECT y las demás notas: propone come back one way como corrección y no la aplica en corrected_text. |
| Qwen / A2-C008 | `review.clean_text_handling`: `2` → `0`; `review.verdict`: `INVALID_CASE` → `PARTIAL`. Consejo potencialmente útil, pero is_correct=false lo presenta como error. Se conserva el caso. |
| Qwen / A2-C010 | `review.clean_text_handling`: `2` → `0`; `review.verdict`: `INVALID_CASE` → `PARTIAL`. Consejo potencialmente útil, pero is_correct=false lo presenta como error. Se conserva el caso. |

La propuesta numérica para las cuatro últimas fichas fue expuesta completa en el chat y el investigador respondió: «Sí, esas notas reflejan mi juicio». No se sustituyó ese consentimiento por un juicio de IA. Las cuatro primeras se aplicaron conforme a su aclaración explícita sobre originales correctos y notas 2/true.

La convención del investigador acepta 2/true en explicación para controles con feedback vacío o sin explicación de un error real. Se conserva su decisión; no debe interpretarse como evidencia de que se produjo una explicación gramatical. NA tampoco se convierte en 2 en otras fichas.

En Gemma A2-C013, CORRECT es el juicio humano sobre el contenido lingüístico. El objeto vacío en `errors` y la envoltura Markdown siguen siendo problemas técnicos: este juicio no vuelve estricto o coherente su JSON. En Qwen A2-C013 se conserva INCORRECT por la corrección propuesta y su desincronización. En A2-C008/C010, PARTIAL permite reconocer el posible valor del consejo sin aceptar que una preferencia estilística sea un error del original.

## Comparación con el ingreso original

| Configuración | Media original /2 | Media aclarada /2 |
|---|---:|---:|
| Qwen3.5-4B Q4_K_M | 1.9122 | 1.8950 |
| Gemma E2B UD-Q4_K_XL | 1.8283 | 1.8450 |
| MiniCPM5-2B Q4_K_M | 1.7497 | 1.7497 |

Las medias de las cuatro primeras fichas siguen siendo 2: cambió la aplicabilidad de criterios, no su juicio favorable. Las cifras antiguas y el subconjunto provisional de 53 casos se conservan en [el informe de ingreso](human_review_results_20261109.md), superado para este cierre por el presente documento.

## Trazabilidad y límites

Capa importada: `analysis_v2/results_120/human_layers/kevin01_clarified_20261109_v1/`. Respaldo derivado, JSONL, metadatos, registro de cambios e informe estructurado: `analysis_v2/human_review_20261109/clarified_v1/`. Ledger de confirmación: `analysis_v2/human_review_20261109/clarifications_v1.json`.

Los cambios se aplican solo si coinciden el SHA del respaldo, el revisor, el ID y cada valor anterior. Después se valida el contrato completo, el crosswalk, los hashes de respuestas, el JSONL y sus metadatos. Los 172 registros no señalados permanecen exactamente iguales. La capa humana es independiente: no se actualizan las métricas automáticas ni sus flags históricos de confirmación.

La muestra son 60 casos de desarrollo repetidos en tres configuraciones, enriquecida en controles, con un único revisor que es el investigador. No hay evidencia de acuerdo interevaluador, superioridad estadística ni precisión poblacional. Los puntajes no se extrapolan a otras cuantizaciones o a LFM. No se ejecutaron inferencias ni se accedió al test final.

La política de sugerencias opcionales y los prompts nuevos permanecen documentados en [el seguimiento de prompts](human_review_prompt_followup_20261109.md). Esta aclaración de notas anteriores no demuestra que los prompts nuevos mejoren las respuestas.

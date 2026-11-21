# Validación previa de los 200 casos

17 de noviembre de 2026. Preparada antes de la primera respuesta del conjunto.

Benchmark SHA-256: `ecfe10cf6942788bfa059379e0461ab9e6291a00b5ef330bc806d94cb21dc125`.
Manifiesto SHA-256: `9ec595218c105e6a2b48d515dcffd01bbfd762b94646b2958f5f972b987e9878`.

| Nivel | Incorrectos | Controles | Palabras mín./máx. | Media |
|---|---:|---:|---:|---:|
| A1 | 75 | 25 | 26 / 36 | 31.11 |
| A2 | 75 | 25 | 33 / 46 | 37.51 |

150 textos incorrectos y 50 controles. Distribución conjunta 84/40/20/6 textos con 1/2/3/4 errores: 248 instancias intencionales. Las ediciones ERRANT pueden tener otra granularidad.

Se cubren 31 categorías de la taxonomía normalizada. Hay alternativas completas prelicenciadas en 29 casos.

Las comprobaciones de esquema lógico, cuotas, longitudes, unicidad de spans, solapamientos y reconstrucción terminaron sin incidencias. No se encontraron candidatos con los umbrales SequenceMatcher 0,78 / trigramas 0,45 contra los 160 textos anteriores o dentro del conjunto. Esto no prueba ausencia de paráfrasis; se separaron dos borradores cercanos detectados manualmente.

Un agente Luna6 max redactó cada nivel; el otro revisó sus 100 casos. Los informes independientes se vinculan a los SHA finales y declaran cero hallazgos abiertos. Las reparaciones se hicieron antes de generar respuestas. No hay validación humana del gold. Las resoluciones y el registro A2 conservan las decisiones y ejemplos antes/después.

| Categoría | Instancias |
|---|---:|
| ARTICLE | 14 |
| BASIC_CONNECTOR | 5 |
| BASIC_FUTURE | 6 |
| BASIC_LEXICAL_CHOICE | 2 |
| BASIC_MODAL | 7 |
| BE_FORM | 10 |
| CAPITALIZATION | 9 |
| COMPARATIVE | 5 |
| CONTRACTION | 5 |
| COUNTABLE_UNCOUNTABLE | 5 |
| MUCH_MANY | 6 |
| NEGATION | 7 |
| OBJECT_PRONOUN | 7 |
| PAST_SIMPLE | 44 |
| POSSESSIVE | 7 |
| PREPOSITION_PLACE | 4 |
| PREPOSITION_TIME | 9 |
| PRESENT_CONTINUOUS | 9 |
| PRESENT_PERFECT | 4 |
| PRESENT_SIMPLE | 5 |
| PUNCTUATION | 1 |
| QUESTION_FORM | 8 |
| SINGULAR_PLURAL | 12 |
| SOME_ANY | 1 |
| SPELLING | 17 |
| SUBJECT_PRONOUN | 6 |
| SUBJECT_VERB_AGREEMENT | 14 |
| SUPERLATIVE | 3 |
| VERB_PATTERN | 9 |
| VERB_PREPOSITION | 4 |
| WORD_ORDER | 3 |

El protocolo prospectivo está en [finalists_200_protocol_20261117.md](../documentation/finalists_200_protocol_20261117.md). La revisión de código y ocho fixtures de seguridad están documentados en [code_review.md](code_review.md). Los 24 artefactos históricos de Fase 1 permanecen byte-idénticos.

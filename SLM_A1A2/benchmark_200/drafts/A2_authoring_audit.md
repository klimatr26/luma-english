# Auditoría de autoría — A2

Fecha: 2026-11-17.

## Cobertura
- 100 casos con consignas únicas: `T200-A2-E001`–`T200-A2-E075` y `T200-A2-C001`–`T200-A2-C025`.
- 75 textos incorrectos: 42 con un error, 20 con dos, 10 con tres y 3 con cuatro; total: 124 errores.
- 25 controles correctos, sin cambios necesarios.
- Longitud de `student_text`: 33–46 palabras; contadas con secuencias de letras y dígitos, permitiendo apóstrofos y guiones internos.

## Revisión lingüística y estructural
- Revisé lingüísticamente los 100 textos, las correcciones y los controles. La lectura buscó errores estructurales u ortográficos claros, preservación del significado, gramática inequívoca en los controles y fragmentos de error distinguibles.
- Cada fragmento `original` aparece exactamente una vez en su texto; los fragmentos de cada caso no se solapan; las sustituciones reconstruyen `corrected_text` exactamente. La comprobación estructural en Python terminó sin incidencias.
- Los controles permanecen idénticos en `student_text` y `corrected_text`, llevan `condition: correct`, `is_correct: true` y `errors: []`.
- Se registran cinco alternativas completas licenciadas: E005, E028, E055, E059 y E075. Incluyen variantes correctas de la construcción partitiva, de `because/so`, de `much/a lot of information` y de `start learning/start to learn`.
- La lectura final no encontró comma splices en los textos corregidos. No hay errores de `some/any` basados solo en polaridad ni juicios de orden adverbial marcado. Las correcciones de conector eliminan la duplicación causal `because ... so` y conservan la coma tras la cláusula inicial.

## Taxonomía
Se usaron 30 de las 31 categorías definidas en `benchmark_120_schema.json`. `SOME_ANY` tiene un caso partitivo estructural (`some of clean towels`), no una distinción basada solo en polaridad. `WORD_ORDER` quedó sin casos para evitar juicios dependientes del orden marcado.

| Categoría | Errores |
|---|---:|
| `ARTICLE` | 5 |
| `BASIC_CONNECTOR` | 2 |
| `BASIC_FUTURE` | 3 |
| `BASIC_LEXICAL_CHOICE` | 1 |
| `BASIC_MODAL` | 3 |
| `BE_FORM` | 5 |
| `CAPITALIZATION` | 4 |
| `COMPARATIVE` | 1 |
| `CONTRACTION` | 2 |
| `COUNTABLE_UNCOUNTABLE` | 2 |
| `MUCH_MANY` | 2 |
| `NEGATION` | 3 |
| `OBJECT_PRONOUN` | 2 |
| `PAST_SIMPLE` | 38 |
| `POSSESSIVE` | 2 |
| `PREPOSITION_PLACE` | 2 |
| `PREPOSITION_TIME` | 4 |
| `PRESENT_CONTINUOUS` | 4 |
| `PRESENT_PERFECT` | 4 |
| `PRESENT_SIMPLE` | 2 |
| `PUNCTUATION` | 1 |
| `QUESTION_FORM` | 3 |
| `SINGULAR_PLURAL` | 6 |
| `SOME_ANY` | 1 |
| `SPELLING` | 3 |
| `SUBJECT_PRONOUN` | 3 |
| `SUBJECT_VERB_AGREEMENT` | 7 |
| `SUPERLATIVE` | 1 |
| `VERB_PATTERN` | 6 |
| `VERB_PREPOSITION` | 2 |

## Originalidad y variantes
- Comparé los 100 `student_text` con los 160 textos permitidos de `benchmark_development_120_v1.json` y `benchmark_smoke_test_v2.json`. No hubo coincidencias exactas; la mayor similitud Jaccard de trigramas fue 0.051 (C024 frente a A2-E02), por vocabulario cotidiano de compras. La medición es un filtro léxico, no una prueba semántica.
- La revisión identificó y reescribió temas repetidos con el conjunto permitido; no se consultaron respuestas ni resultados de modelos.
- Se aceptan variantes estándar británicas y estadounidenses. Entre los ejemplos están `queue`, `flat`, `favourite`/`colour` y `center`.

## Estado de aprobación
Revisión lingüística realizada por el agente que redactó el borrador. No hay aprobación humana registrada ni se afirma que exista.

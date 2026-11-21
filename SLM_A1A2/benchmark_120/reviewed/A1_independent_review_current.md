# Revisión lingüística independiente A1 — versión actual

**Archivo auditado:** `SLM_A1A2/benchmark_120/reviewed/A1_cases.json`
**SHA-256 del JSON revisado:** `E2B7075B3DB86D75A44F8A1ACCAA771359A7D44DD5AB4E570B470D7CCF56F50C`
**Cobertura:** 60/60 IDs (45 incorrectos y 15 controles), A1-E001–A1-E045 y A1-C001–A1-C015.

Leí cada tarea, texto, error, corrección, explicación, alternativa y control de la versión indicada por el hash. La revisión previa `A1_editorial_audit.md` se usó solo como contexto; las decisiones de abajo corresponden al contenido presente. No ejecuté inferencias ni miré resultados de modelos. No edité el JSON, Fase 1 ni el test final. Este informe es el único archivo creado por esta revisión. El recuento e IDs actuales son 60 casos, 60 IDs únicos, 45 `incorrect` y 15 `correct`; los controles conservan `corrected_text == student_text` y `errors == []`.

## Revisión de los cambios posteriores

1. **A1-E001 — falso positivo original, reparación por IA verificada.** En el hash anterior `5D08CA660B07CD3B108A5A06A8C041DEF900DE73402E63454ABBCE7A242C360E`, el sujeto era `our art club`. La concordancia plural `our art club meet` puede ser estándar en inglés británico cuando el colectivo se concibe como sus miembros reunidos semanalmente; la política acepta BrE, así que ese tramo no podía puntuarse como error. La versión actual cambia el sujeto a `our art teacher`, y `art teacher meet` sí es inequívocamente incorrecto. Verifiqué que el cambio mantiene dos instancias y que las formas del gold ahora concuerdan con el texto. Cambridge English Grammar Today confirma la concordancia singular o plural con ciertos colectivos según se entiendan como unidad o como miembros ([Collective nouns](https://dictionary.cambridge.org/grammar/british-grammar/collective-nouns)). **La reparación actual es de IA; no representa aprobación humana ni sign-off final.**

2. **A1-E005 — resuelto.** `acceptable_corrections` ahora contiene `my cousin's room` y `my cousins' room`; se añadió el texto completo plural en `acceptable_alternatives`, y la explicación dice que el texto no fija el número de primos. Ambas lecturas quedan admitidas.

3. **A1-E006 y A1-E026 — resueltos.** Ambos golds ahora aceptan conservar `and` para adición o `but` para el contraste plausible, incluyen la alternativa completa y explican que el defecto es la secuencia de dos coordinadores, no la relación contrastiva. La detección de error sigue siendo inequívoca.

4. **A1-E019 — resuelto.** `a lot of grapes` ahora aparece como corrección local aceptable y como alternativa de texto completo junto con `many grapes`.

5. **A1-E033 — resuelto.** El gold acepta `at the shop` y `at a shop`, incluye la alternativa completa con `a`, explica que la elección depende de si se habla de un lugar específico o no y usa el subtipo neutral `missing_determiner_before_singular_countable_place`.

6. **A1-E040 — reparación por IA verificada.** La versión anterior imitaba de cerca el patrón de smoke A1-E12 (`I no like ...`). La actual usa una regla de museo: `The museum guide no allow food inside the picture rooms...`; la corrección `guide does not/doesn't allow` es clara y el resto del texto es coherente. Se mantiene un solapamiento de habilidad general con A1-E12 (negación del presente simple sin auxiliar), pero el contexto, los sujetos, los verbos y el contenido ya son distintos. Esta reparación fue hecha por IA; no constituye aprobación humana.

7. **A1-E012 — revisión de la nueva versión.** La petición directa `can you bring ...` requiere `?`, la oración declarativa final lleva punto y `will puts` debe ser `will put`. El nuevo contenido (reunión del club, marcadores, letrero para el gimnasio y futuro) es coherente con la tarea y no contiene otros errores. El inicio comparte con A1-E026 el marco `Hi [name], can you bring [item] to [place] [time]`, acorde con el acto comunicativo de pedir que alguien traiga algo; la segunda parte y el contexto difieren. La similitud del artefacto `strict_validation_120.json` corresponde a una versión anterior de ambos casos y debe recalcularse con este JSON antes de usarse como evidencia vigente.

Los cinco puntos anteriores sobre alternativas, explicación y subtipos quedaron resueltos en el JSON actual. No encontré errores lingüísticos inequívocos sin marcar, golds que penalicen una lectura estándar ni controles incorrectos.

## Dictamen por ID

`OK` = gold lingüísticamente defendible; `REVISAR` = error válido, con alternativa o lectura que conviene registrar; `IA-REPARADO` = defecto de la versión anterior ya corregido en el JSON del hash actual.

| ID | Dictamen | Justificación |
|---|---|---|
| A1-E001 | IA-REPARADO | `art teacher meet` exige `meets`; `Lina bring` exige `brings`. El antiguo `art club meet` admitía concordancia colectiva BrE y fue sustituido. |
| A1-E002 | OK | Los numerales cinco y dos requieren plurales contables: `postcards`, `shells`. |
| A1-E003 | OK | `a/an` se determina por el sonido inicial: `an old clock`, `a small bird`. |
| A1-E004 | OK | `I` es el pronombre sujeto y `us` el objeto de `gives`; la alternativa `practice` cubre AmE. |
| A1-E005 | OK | El gold acepta posesivo singular y plural, usa un subtipo neutral y explica que el número de primos no está fijado. |
| A1-E006 | OK | Los errores de preposición y concordancia son claros; el doble coordinador es defectuoso y ahora admite las dos reparaciones plausibles. |
| A1-E007 | OK | `a word game` es la frase nominal prevista y `about` debe preceder a `animals`; ambas correcciones conservan el contenido de la tarea. |
| A1-E008 | OK | Las preguntas directas en presente simple requieren `does` y verbo base en ambas preguntas. |
| A1-E009 | OK | La negación estándar con `I` usa `don't` antes del verbo base; `maths` no se marca como variante. |
| A1-E010 | OK | `any of` requiere un complemento definido (`any of the paper plates`); también vale eliminar `of`. |
| A1-E011 | OK | `wear my breakfast` no expresa la acción prevista; `eat my breakfast` es la colocación adecuada. |
| A1-E012 | OK | La petición directa `can you bring...` requiere signo de interrogación; el statement final requiere punto; después de `will` va el verbo base `put`. Queda un marco de petición compartido con E026, no un error gramatical adicional. |
| A1-E013 | OK | `children` requiere `are` y `their father` requiere `is` en el presente continuo. |
| A1-E014 | OK | La tarea y `now` apoyan la acción en curso: `Our rabbit is sleeping`. |
| A1-E015 | OK | El sujeto plural `neighbors` toma `invite`, sin `-s`. |
| A1-E016 | OK | `owl` comienza con sonido vocálico, por lo que corresponde `an owl`. |
| A1-E017 | OK | `into` expresa movimiento; `are` describe ubicación estática dentro del cajón, que requiere `in`. |
| A1-E018 | OK | `becaus` es una falta ortográfica; la alternativa completa `favourite` es una variante BrE válida. |
| A1-E019 | OK | `much` no modifica el plural contable `grapes`; el gold admite tanto `many grapes` como `a lot of grapes`. |
| A1-E020 | OK | `most easiest` combina dos formas superlativas; `the easiest` es la corrección estándar. |
| A1-E021 | OK | `Yesterday` fija el pasado; `go` y `see` deben ser `went` y `saw`, incluso con el colectivo `class`. |
| A1-E022 | OK | `wait` requiere `for` en este sentido; después de `will` va `swim`; el pronombre `I` se escribe en mayúscula. |
| A1-E023 | OK | `it's` significa `it is`; el posesivo de la pelota es `its`. |
| A1-E024 | OK | `more smaller` duplica la marca comparativa; `fewer pockets` ya es correcto y no se altera. |
| A1-E025 | OK | El plural ortográfico de `sandwich` se escribe `sandwiches`. |
| A1-E026 | OK | El punto en la petición directa es puntuación; el doble coordinador es defectuoso y el gold admite la lectura aditiva con `and` y el contraste plausible con `but`. |
| A1-E027 | OK | La pregunta necesita `does` y verbo base; `will to sing` debe perder `to`. |
| A1-E028 | OK | Después de `doesn't` se usa el verbo base `eat`. |
| A1-E029 | OK | `by bicycle` tiene orden fijo; además son claros la mayúscula inicial, el infinitivo sin `to` tras `will` y el plural irregular `children`. |
| A1-E030 | OK | `borrow` es recibir; para pedir que otra persona entregue temporalmente el objeto corresponde `lend`. |
| A1-E031 | OK | `bread` es incontable en este sentido; `many` no lo cuantifica. La mayúscula de `Saturdays` y el verbo base tras `will` son correctos. |
| A1-E032 | OK | `onto` expresa movimiento hacia la silla; para la ubicación ya establecida corresponde `on`. |
| A1-E033 | OK | La omisión de determinante es real y el gold acepta `a shop` y `the shop`, con explicación y subtipo que no presuponen contexto previo. |
| A1-E034 | OK | El numeral `three` requiere el plural `tomatoes`; `one cucumber` es correcto. |
| A1-E035 | OK | `my aunt` es sujeto singular y requiere `works`. |
| A1-E036 | OK | La preposición `to` rige el pronombre objeto `me`, no `I`. |
| A1-E037 | OK | La tarea fija un solo hermano, así que el posesivo singular `brother's` está bien determinado. |
| A1-E038 | OK | La pregunta en presente simple con `you` requiere `do` antes del sujeto. |
| A1-E039 | OK | `is` necesita la forma en `-ing` para la acción que ocurre en la imagen. |
| A1-E040 | IA-REPARADO | `guide no allow` es una negación no estándar; con el sujeto singular corresponde `guide does not/doesn't allow`. El nuevo contexto de regla de museo se distingue del antiguo texto similar a smoke A1-E12, aunque conserva la misma habilidad objetivo general. |
| A1-E041 | OK | En este sentido, `listen` lleva `to` antes de su objeto. |
| A1-E042 | OK | `visit` va seguido de su objeto y `by bus` es la frase de medio; `will to bring` y `my sister and I helps` también son errores claros. |
| A1-E043 | OK | La colocación estándar es `do my homework`, no `make my homework`. |
| A1-E044 | OK | `Yesterday` fija el pasado y el irregular correcto es `swam`. |
| A1-E045 | OK | `Ben` requiere mayúscula, `because of` no introduce la cláusula finita `my swimming lesson finishes`, y `will` lleva verbo base; el punto final es puntuación, no gramática. |
| A1-C001 | OK | El presente simple, los objetos y `often ask` están bien formados. |
| A1-C002 | OK | `neighbour` y `lift` son variantes BrE válidas; el plural `they go` está bien. |
| A1-C003 | OK | `at four`, `at half past three` y `on Wednesdays` usan preposiciones temporales correctas. |
| A1-C004 | OK | `wants no lettuce` es gramatical aunque marcado; no es un error que deba corregirse. |
| A1-C005 | OK | `sometimes go` y `usually walk` tienen orden de adverbio natural; el resto es correcto. |
| A1-C006 | OK | Las colocaciones de ropa, ubicación y `put them on` son correctas. |
| A1-C007 | OK | `sheep` mantiene la misma forma en plural; artículos y concordancia son correctos. |
| A1-C008 | OK | `in a pocket`, `inside my school bag` y `next to` expresan ubicaciones válidas. |
| A1-C009 | OK | `nobody hides` lleva concordancia singular y las frases del juego son naturales. |
| A1-C010 | OK | La secuencia de tareas domésticas mantiene tiempos y concordancia correctos. |
| A1-C011 | OK | `get off`, `near a café` y el resto del trayecto son expresiones válidas. |
| A1-C012 | OK | El sujeto compuesto toma `sit`; `sometimes comes` y `sleeps` concuerdan con `cat`. |
| A1-C013 | OK | `At the weekend` es BrE válido y el colectivo `family buys` es una concordancia singular correcta. |
| A1-C014 | OK | El posesivo `uncle's` y la narración en pasado son correctos; la tarjeta cumple la tarea. |
| A1-C015 | OK | `practise` es la grafía verbal BrE; no hay error de forma ni de significado. |

## Alcance del dictamen

La única clasificación que habría generado un falso positivo lingüístico en una versión anterior fue E001; está corregida por IA en el archivo actual. Las revisiones posteriores de E040 y E012 cambian el contenido para reducir similitudes con smoke A1-E12 y con E026, respectivamente; el solapamiento residual de habilidad en E040 y de marco comunicativo en E012 queda documentado para recalcular la similitud sobre la fuente actual. Los ajustes de alternativas, explicaciones y subtipos quedan incluidos en el SHA indicado. E012, E026 y E045 incluyen puntuación; esos tramos pueden respaldar una evaluación de puntuación, pero por sí solos no acreditan recuperación gramatical. La auditoría lingüística queda cerrada para el SHA indicado; este dictamen no es aprobación humana ni congelación del conjunto.

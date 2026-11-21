# A2 editorial audit — benchmark120 Fase 2 (60 casos)

Alcance: `benchmark_120/reviewed/A2_cases.json` (60 casos: A2-E001…E045 incorrectos, A2-C001…C015 controles) y este informe.
Base leída: drafts `A2_errors_001_015.json`, `A2_errors_016_030.json`, `A2_errors_031_045.json`, `A2_controls_001_015.json`.
No se leyó `A2_controls_016_030.json` (excluido por encargo) y no se editó ningún raw, normalizer ni validator.
Esto es un juicio editorial de trabajo, no una aprobación final del benchmark.

## 1. Resultado de verificación (calculado, no declarado)

- IDs: 60/60 exactos (45 incorrectos + 15 controles), sin duplicados.
- Distribución de incorrectos: 25 textos con 1 error, 12 con 2, 6 con 3, 2 con 4 → 75 instancias. Exacta según encargo.
- Longitud (regex del validator `count_words`): min 35, mediana 46.5, max 59; todo en 25–100. `length_words` recalculados en cada ronda (ronda 0: A2-E021 45→47; ronda 2: E013→45, E022→49, E032→52, E034→51).
- Taxonomía: los 31 tipos normalizados presentes; ningún error fuera de taxonomía.
- Fragmentos: cada `original` aparece literalmente y exactamente 1 vez en `student_text`; cada `correction` aparece en `corrected_text`; sin solapes; la sustitución simultánea de todos los fragmentos reconstruye `corrected_text` en los 45 incorrectos.
- Controles: 15/15 con `errors: []`, `is_correct: true`, `corrected_text` idéntico a `student_text`, sin alternativas.
- Exclusión Fase 1: comparación normalizada + `SequenceMatcher` contra los 40 del smoke (solo IDs y puntuaciones, sin copiar ni parafrasear): 0 reutilizaciones exactas, 0 candidatos ≥ 0.78, 0 duplicados internos.

## 2. Distribución por tipo (75 instancias)

ARTICLE 3, BASIC_CONNECTOR 3, BASIC_FUTURE 2, BASIC_LEXICAL_CHOICE 1, BASIC_MODAL 3, BE_FORM 4,
CAPITALIZATION 2, COMPARATIVE 3, CONTRACTION 1, COUNTABLE_UNCOUNTABLE 2, MUCH_MANY 3, NEGATION 1,
OBJECT_PRONOUN 3, PAST_SIMPLE 7, POSSESSIVE 1, PREPOSITION_PLACE 2, PREPOSITION_TIME 2,
PRESENT_CONTINUOUS 2, PRESENT_PERFECT 2, PRESENT_SIMPLE 1, PUNCTUATION 1, QUESTION_FORM 4,
SINGULAR_PLURAL 2, SOME_ANY 3, SPELLING 1, SUBJECT_PRONOUN 1, SUBJECT_VERB_AGREEMENT 2,
SUPERLATIVE 2, VERB_PATTERN 5, VERB_PREPOSITION 4, WORD_ORDER 2.

Se redujo la concentración en pasado/concordancia (PAST_SIMPLE 7/75; SUBJECT_VERB_AGREEMENT 2/75, BE_FORM 4/75 como forma separada) y se cubren conectores básicos inequívocos (3 dobles although/but y because/so en E016, E026, E032), preguntas (4 QUESTION_FORM), contabilidad (MUCH_MANY 3 + COUNTABLE_UNCOUNTABLE 2 + SOME_ANY 3 + SINGULAR_PLURAL 2), future de forma (2 BASIC_FUTURE con will+base), comparativos/superlativos (3+2), perfect (2) y patterns (5).

## 3. Cambios por ID (respecto a drafts recibidos)

- A2-E001: tipos normalizados a PAST_SIMPLE (`taked`→`took`) y NEGATION (`didn't remembered`→`didn't remember`, con alternativa `did not remember`). Sin cambio de texto.
- A2-E002/E003: sin cambios salvo tipo/explicación ya conformes.
- A2-E004: rediseñado tras revisión del reviewer general (ronda integrador). Contra mi juicio previo: el orden `sujeto + every evening + verbo` es inglés gramatical marcado (adjunto temporal entre sujeto y verbo permitido), no un falso positivo apto para el benchmark. Nuevo error inequívoco con la time-phrase rota por el PP: `My sister practises the piano every in the living room evening` → `My sister practises the piano in the living room every evening`. Se preserva `practises` (BrE) y se acepta `practices` (AmE). `corrected_text` sin cambios.
- A2-E005: ambos errores a QUESTION_FORM (`do`-support presente y pasado). Sin cambio de texto.
- A2-E006: `My aunt are`→BE_FORM; `two children is drawing`→PRESENT_CONTINUOUS. Sin cambio de texto.
- A2-E007–E014: E013 rediseñado (ronda 2, ver §6); resto sin cambios de texto salvo E008, cuya task se retitula a pet-sitting/devolución de llaves (`Write about looking after a neighbor's cat and returning their keys`), que describe el contenido real (alimentar al gato, enviar foto, devolver llaves); tipos normalizados (VERB_PREPOSITION, OBJECT_PRONOUN, CONTRACTION con alternativa `It is…`, BASIC_MODAL, SUPERLATIVE, PRESENT_PERFECT, SOME_ANY, VERB_PATTERN).
- A2-E015: reescrito según encargo. Nota: los drafts recibidos no contenían en E015 la frase citada (`I practise every evening the difficult parts…`); E015 era un caso de puntuación sobre una granja. Ronda integrador: el patrón original verbo-objeto separado (`practise every evening the…`) puede ser pesado/marcado pero formal válido, así que se adopta la time-phrase rota preferida por el integrador con el mismo tema: `I practise every on my guitar evening the difficult parts` → `I practise the difficult parts on my guitar every evening`, cambio mínimo que preserva contenido. Forma primaria mínima (end-position); alternativas full-text con `Every evening` frontalizado (BrE y AmE) en `acceptable_alternatives`, más variante AmE `practice` a nivel de fragmento y de texto completo. No se impone estilo. La cobertura de PUNCTUATION queda solo en E029.
- A2-E016 (1→3 errores): se mantiene `digged`→`dug` y se añaden conector inequívoco (`Although…, but…`→ quitar `but`, con alternativa de reestructuración) y future de forma (`will to come`→`will come`). Texto reescrito mínimamente en el mismo huerto comunitario.
- A2-E017/E018/E019/E020: sin cambios de texto; E017 acepta `farther`/`further`; E019 a PRESENT_CONTINUOUS.
- A2-E021 (1→3): se mantiene la pregunta (`What time…`→QUESTION_FORM) y se añaden SUBJECT_PRONOUN (`Me and my brother`→`My brother and I`) y BASIC_LEXICAL_CHOICE (`lend one from`→`borrow one from`). Reescritura mínima en la misma clase de música.
- A2-E022 (1, rediseñado ronda 2, ver §6): `don't have some yellow paper` admitía lectura gramatical; nuevo original `don't have any of yellow paper`→`don't have any yellow paper` (licencia `don't have any of the yellow paper`). Tipo SOME_ANY, subtype `partitive_determiner`. `corrected_text` sin cambios. E023 sin cambios.
- A2-E024 (1→3): se mantiene `on the entrance`→`at the entrance` (PREPOSITION_PLACE) y se añaden PRESENT_SIMPLE (`cafe stay`→`cafe stays`) y CAPITALIZATION (`fridays`→`Fridays`). Misma escena de cine.
- A2-E025: sin cambios.
- A2-E026 (1→3, rediseñado en rondas 1–2): ronda 2 divide ante Because porque el original `…year, because…, so…` aún podía leerse como 3 cláusulas válidas. Estudiante: `I have went there again this year. Because my cousin joined us, so we had a picnic by lake.` Primaria: `I have gone…year. Because my cousin joined us, we had…by the lake.`; alternativa full-text so-only (`…year. My cousin joined us, so we had…`); ambas causas mínimas licenciadas. Artículo inequívoco `by lake`→`by the lake` (se abandona `by water`, debatible). Mismo lago/picnic.
- A2-E027: tipo a POSSESSIVE (`they're`→`their`), aceptando `favourite`/`favorite`. Sin cambio de texto.
- A2-E028/E029/E030: sin cambios; E029 conserva `programme` (BrE) sin penalizar y se mantiene como caso de puntuación de punto final, tipo distinto dentro de PUNCTUATION, sin atribuirle poder de discriminación gramatical.
- A2-E031: sin cambios de texto; `We was`→BE_FORM, resto PAST_SIMPLE.
- A2-E032 (2→4, rediseñado ronda 2, ver §6): (a) retracto `by foot` como error —es variante AmE frecuente válida—; nuevo idiom fijo roto `go there at foot`→`go there on foot` (PREPOSITION_PLACE). (b) retracto `arrived in the station` —válido como interior—; nueva omisión `arrived the station`→`arrived at the station` (VERB_PREPOSITION). (c) split de la primaria con comma splice: `Tomorrow I will to take an earlier bus. Although it is early, but I do not want to be late.` → `…will take…. Although…, I do not want…`. Mismo viaje a la estación.
- A2-E033: `a little carrots`→COUNTABLE_UNCOUNTABLE, `two onion`→SINGULAR_PLURAL. Sin cambio de texto.
- A2-E034 (1→3, ronda 2, ver §6): retracto `on next Monday` —aceptable dialectal/native—. Nuevo original `I will post it in Monday morning`→`I will post it on Monday morning` (PREPOSITION_TIME, subtype `preposition_on_days`); sin `next` porque la fuente nueva no lo trae. Misma oficina de correos.
- A2-E035/E036: sin cambios; E035 SVA+ARTICLE, E036 SVA (`nobody have`→`nobody has`).
- A2-E037 (1→3, ronda 2): el temporal pasa a `can't go in Thursday morning`→`can't go on Thursday morning` (cita definida el Thursday); se licencia `that day` en la alternativa full-text existente. Se mantienen COUNTABLE_UNCOUNTABLE (`informations`→`information`) y CAPITALIZATION (`friday`→`Friday`). Misma cita con el dentista.
- A2-E038–E045: sin cambios de texto; tipos normalizados (p. ej. E040 `enjoyed to sit…`→VERB_PATTERN, E041 `reached to`→VERB_PREPOSITION y `players was`→BE_FORM, E045 `There was many`→BE_FORM).
- Controles A2-C001…C015: correctos y sin cambios salvo dos endurecimientos mínimos aplicados idénticamente a `student_text` y `corrected_text`: C002 `cooking book`→`cookbook` (forma estándar en ambas variantes) y C005 `when I got out the evening before`→`when I got home the evening before` (evita un aparente complemento ausente). Juicio: los 15 son correctos, difíciles y naturales — perfectos con `since`/`already`/`yet` (C001, C006), condicional real (C006), gerundios tras `enjoy`/`forward to`/`practise` (C008, C012, C015), `let + bare infinitive` (C012), negación (C003, C015), orden de adverbios (C012 `spoke slowly`), `lend/borrow` bien discriminado (C002, C004), cuantificadores (C003 `a little`/`a few`, C014 `plenty of sunlight`) y preposiciones (`at the traffic lights`, `in charge of`, `opposite the park`).

## 4. Política de variantes BrE/AmE

No se impone estilo: se conservan `practise(s)`/`favourite`/`colourful`/`travelled`/`tyres`/`programme`/`afterwards`/`At weekends` (BrE) y `neighbors`/`neighborhood` (AmE) sin marcarlos como error; las alternativas aceptan `practice(s)`, `favorite`, `further`, `kilometers`, `It is…`, `did not…`, `that day`. Casos testigo: E004, E015, E027, E034, E001, E037, C007, C012.

## 5. Método y límites

Checks ejecutados: IDs/estratos, `length_words` con la regex del validator, taxonomía, literalidad/unicidad/no-solape de fragmentos, reconstrucción de `corrected_text` por sustitución simultánea, identidad de controles, y similitud contra smoke (umbral 0.78). Tras la ronda 2 (E013, E022, E026, E032, E034, E037): distribución intacta 25/12/6/2 (75 instancias), 31 tipos, palabras 35–59 (mediana 46.5), 0 errores de verificación, 0 flags smoke, 0 duplicados; `length_words` recalculados (E013 45, E022 49, E032 52, E034 51). Sin inferencias, sin test de ~200, sin outputs de modelos, sin operaciones Git. Queda para el coordinador/integrador confirmar la consolidación con A1 y el congelamiento.

## 6. Segunda ronda del integrador — retractaciones de juicio previo

Strict-grammar, no style. Retiro explícitamente estos juicios anteriores; los originales nuevos son inequívocos en BrE/AmE/estándar, sin marcar estilo ni forzar lecturas dentro/fuera por imaginación:

- E013/E022: `isn't some cheese` (some específico), `buy any lemons` (free-choice) y `don't have some yellow paper` admitían lecturas gramaticales. Rediseño a partitiva estructural rota (`any of cheese`, `some of lemons`, `any of yellow paper` sin determinante tras *of*); instancias 2+1 y tipo SOME_ANY intactos, subtype `partitive_determiner`; licenciadas `any of the cheese`, `some of the lemons`, `any of the yellow paper`.
- E026: el `because…, so…` en una sola frase aún podía leerse como 3 cláusulas válidas; se divide ante Because. Retiro además `by water` (debible) por `by lake`→`by the lake`.
- E032: retiro `by foot` (variante AmE frecuente válida) y `arrived in the station` (válido como interior); nuevos `at foot` y omisión `arrived the station`. Retiro la primaria con comma splice (`…, although…, …`); split en frases.
- E034: retiro `on next Monday` (aceptable dialectal/native); nuevo `in Monday morning`→`on Monday morning`, sin `next` porque la fuente nueva no lo trae.
- E037: `at this day` sustituido por `in Thursday morning`→`on Thursday morning` (cita definida el Thursday); `that day` sigue licenciado como alternativa full-text.

# Revisión editorial independiente A2 — benchmark de desarrollo

## Alcance y método

Audité los 60 registros de SLM_A1A2/benchmark_120/reviewed/A2_cases.json, incluidos task, student_text, cada fragmento original, correction, explicación y tipo, corrected_text, alternativas y la condición de cada control. Leí el plan de Fase 2 y A2_editorial_audit.md como contexto, pero el juicio lingüístico siguiente se hizo releyendo los datos actuales. No edité el JSON, la Fase 1 ni otro artefacto; no ejecuté inferencias ni abrí el test final.

SHA-256 del JSON auditado: ED40EC9181E340FB86E55F331CCA98F2ACB5B03F3BF4BDA99B0B37340E811279.

Verifiqué mecánicamente IDs y conteos, la política de variantes declarada, la longitud con el cómputo de palabras del validator, la presencia literal única de cada original, el no solapamiento de spans, la presencia de cada corrección, la reconstrucción de los 45 corrected_text mediante sustituciones y la identidad de los 15 controles. Resultado: 60/60 IDs únicos; 45 incorrectos, 15 controles y 75 instancias de error; 31 tipos; longitud 35–59 palabras, mediana 46.5; todos los campos de longitud concuerdan; cero fallos mecánicos. Los 15 controles tienen errors vacío, is_correct true, texto corregido idéntico y ninguna alternativa.

## Dictamen

**0 BLOCKER.** Los 45 errores marcados son errores reales en inglés estándar BrE/AmE; las correcciones principales restauran la forma y conservan el significado. Los 15 controles son gramaticales y conservan lecturas naturales. No encontré errores lingüísticos omitidos que obliguen a reanotar, ni lecturas plausibles que conviertan en correctos los errores diseñados. Hay algunas alternativas de edición que convendría aceptar si el evaluador compara correcciones de forma estricta; se detallan después de la tabla y no invalidan los casos.

## Dictamen por ID

| ID | Dictamen | Razón lingüística |
|---|---|---|
| A2-E001 | OK | taked → took y didn't remembered → didn't remember: pasado irregular y base tras didn't; significado intacto. |
| A2-E002 | OK | more faster duplica la marca comparativa; faster conserva la comparación. |
| A2-E003 | OK | much oranges no concuerda con el sustantivo plural contable; many oranges es la corrección natural. |
| A2-E004 | OK (R1 resuelto) | every … evening queda estructuralmente roto por in the living room. El JSON actualizado licencia el tiempo al final o frontalizado, con variantes BrE/AmE; las dos opciones preservan sentido y tarea. |
| A2-E005 | OK | Dos preguntas directas requieren inversión con do y did; después de did, meet va en base. |
| A2-E006 | OK | aunt are requiere singular is; two children is drawing requiere are drawing para el sujeto plural y la acción actual. |
| A2-E007 | OK | looked the screen y waited the shop omiten las preposiciones exigidas por estos usos: look at, wait for. |
| A2-E008 | OK | she y they ocupan posiciones de objeto; se requieren her y them. La tarea ahora describe tanto cuidar el gato como devolver las llaves. |
| A2-E009 | OK | Its posesivo no puede sustituir a It is en It's a small blue blanket; la explicación y la alternativa expandida son correctas. |
| A2-E010 | OK | should to bring y shouldn't to leave rompen la construcción modal; las formas base conservan el consejo. |
| A2-E011 | OK | most hottest duplica la marca de superlativo; the hottest es la forma estándar. |
| A2-E012 | OK | El presente perfecto requiere participio: have drawn. El contexto de proyecto escolar encaja. |
| A2-E013 | OK | Las dos partitivas con of carecen de determinante: any of the cheese, some of the lemons; las formas sin of también están licenciadas. |
| A2-E014 | OK | enjoy va seguido de gerundio; enjoy cooking es idiomático y preserva el sentido. |
| A2-E015 | OK | La frase temporal está estructuralmente rota; la reparación coloca la frase de tiempo junta. Se aceptan variantes BrE/AmE y el orden frontal con Every evening. |
| A2-E016 | OK | digged es forma irregular no estándar; although … but duplica el conector; tras will va come sin to. Las alternativas de contraste preservan la relación. |
| A2-E017 | OK | more farther duplica el comparativo; se aceptan farther y further. |
| A2-E018 | OK | photographs es plural contable y requiere many, no much. |
| A2-E019 | OK | La descripción está en curso; con el sujeto plural parents corresponde are talking. |
| A2-E020 | OK (R2 resuelto) | El JSON actualizado licencia should check y should be checking. La explicación distingue correctamente should + base check de should + base be + checking; -ing no sigue directamente al modal. La alternativa completa conserva and clean. |
| A2-E021 | OK | Sujeto pronominal, orden de pregunta directa y confusión lend/borrow están bien identificados; borrow one from the teacher concuerda con tomar algo prestado. |
| A2-E022 | OK | any of yellow paper carece del determinante tras of; any of the yellow paper y any yellow paper son opciones gramaticales según la referencia. |
| A2-E023 | OK | enjoy to use requiere gerundio. La repetición del patrón de E014 usa un tema y contexto distintos. |
| A2-E024 | OK | wait at the entrance, concordancia singular cafe stays y mayúscula de Fridays son correctos; no detecté otro error. |
| A2-E025 | OK (R3 resuelto) | most simplest contiene doble superlativo; el JSON actualizado acepta simplest y most simple, ambas formas gramaticales, y explica que debe usarse una sola construcción. |
| A2-E026 | OK | have went requiere participio gone; Because …, so … duplica el conector causal; by lake requiere determinante para el sustantivo singular contable. La alternativa con so conserva el significado. |
| A2-E027 | OK | they're significa they are; se requiere el posesivo their. Se aceptan las dos grafías dialectales de favourite/favorite. |
| A2-E028 | OK | sandwiches es plural contable y requiere many. |
| A2-E029 | INFO R4 | El único error es añadir el punto final. Es un caso válido de PUNCTUATION, pero no evidencia de gramática A2; su valor discriminativo aislado es bajo. |
| A2-E030 | OK | invite someone to do something requiere to; la reparación deja intacto el relato. |
| A2-E031 | OK | Los cuatro spans son errores de pasado inequívocos bajo Last Tuesday: prepare, bringed, was con we y take. put ya tiene la misma forma en pasado. |
| A2-E032 | OK | at foot requiere la expresión fija on foot; arrive no toma aquí objeto directo; will to take requiere base; although … but duplica el contraste. El texto actual no penaliza by foot ni arrived in the station; la oración corregida queda bien separada y no etiqueta un comma splice. |
| A2-E033 | OK | a little carrots no concuerda con el plural contable y two onion requiere plural. El paso de la receta en presente al recuerdo de lo cocinado en pasado es una lectura coherente, no otro error. |
| A2-E034 | OK (R5 resuelto) | El orden de pregunta indirecta y el plural después de two son errores; in Monday morning es incorrecto. El JSON actualizado acepta on Monday morning y Monday morning sin preposición. on next Monday no aparece en el caso. |
| A2-E035 | OK | flatmates share requiere verbo base con sujeto plural; in cupboard necesita determinante en este referente específico. |
| A2-E036 | OK | nobody es singular y requiere has; el presente perfecto y la lectura reportada no introducen otro error. |
| A2-E037 | OK (R6 resuelto) | in Thursday morning, informations y friday son errores. El JSON actualizado licencia on Thursday morning y Thursday morning sin preposición, además de las alternativas completas con that day. |
| A2-E038 | OK | buyed es forma irregular incorrecta y vegetabels tiene error ortográfico; las reparaciones son precisas. |
| A2-E039 | OK | yesterday evening requiere pasado forgot; no hay otro error en el texto. |
| A2-E040 | OK | an small requiere a; enjoyed to sit requiere gerundio y la coordinación paralela sitting … and watching es correcta. |
| A2-E041 | OK | reach lleva objeto directo sin to; el sujeto plural players requiere were. |
| A2-E042 | OK | En este sentido, let + objeto va seguido de verbo base sin to; la corrección conserva el sentido. |
| A2-E043 | OK | Tras la preposición for se usa el pronombre objeto her. |
| A2-E044 | OK | much more colder duplica el comparativo; much colder es la reparación estándar y mantiene la intensificación. |
| A2-E045 | OK | En la construcción existencial, many coats es plural y corresponde there were. El cambio entre la descripción general y el episodio pasado es coherente. |
| A2-C001 | OK | since con presente perfecto, has been, expresa un cambio iniciado con la apertura del puente; las referencias de tiempo concuerdan. |
| A2-C002 | OK | cookbook es una grafía estándar; borrowed/returned/lending distingue correctamente prestar y tomar prestado. |
| A2-C003 | OK | a little water y a few pages usan cuantificadores adecuados; las condicionales y el orden de palabras son naturales. |
| A2-C004 | OK | lends, borrow y have to bring … back están bien construidos; el texto y la tarea coinciden. |
| A2-C005 | OK | El pasado perfecto sitúa had dropped antes de encontrar el pase; when I got home y la referencia temporal son naturales. |
| A2-C006 | OK | Primer condicional correcto, presente perfecto con already/yet y futuro en la consecuencia. |
| A2-C007 | OK | Rutina en presente simple y subordinada con although correctas; At weekends es una variante aceptada. |
| A2-C008 | OK | used to contrasta el hábito pasado con la rutina actual; When there is enough refiere correctamente a money. |
| A2-C009 | OK | what to do, condicional de regla y gerundios coordinados tras practised son correctos. |
| A2-C010 | OK | El gerundio funciona como sujeto; comparativos, unless y las referencias al transporte son naturales. |
| A2-C011 | OK | Every spring, Last year y this year corresponden a tiempos verbales coherentes. |
| A2-C012 | OK | Pasado perfecto, let + objeto + base, adverbio slowly y afterwards son correctos; practise es BrE válido. |
| A2-C013 | OK | Las instrucciones imperativas y las preposiciones de ubicación son gramaticales; too far encaja con la dirección. |
| A2-C014 | OK | plenty of sunlight y las referencias temporales pasado/presente son correctas. |
| A2-C015 | OK | have only been twice y look forward to the next meeting están bien formados; no hay error adicional. |

## Cierre de las cinco observaciones

- **R1 — E004, resuelta en el JSON:** se aceptan las frases temporales al final o frontalizadas, con practises/practices. La estructura every … evening del original permanece inequívocamente rota.
- **R2 — E020, resuelta en el JSON:** acceptable_corrections incluye should be checking y acceptable_alternatives incluye la oración completa “You should be checking the tyres every week and clean the chain after a muddy ride.” La explicación ahora especifica should + infinitivo base check o should + auxiliar base be + checking; no permite -ing directamente después de should. Esta secuencia modal + auxiliar + gerundio concuerda con [Cambridge English Grammar Today, “Verb phrases”](https://dictionary.cambridge.org/us/grammar/british-grammar/verb-phrases). La variante local es gramatical y pertinente al consejo. El predicado clean queda como verbo base coordinado bajo should; es menos paralelo que checking and cleaning, pero gramatical, y se mantiene fuera del span. Si un modelo produce exactamente esa alternativa, la rúbrica §1/§5 la deja como máximo en PARTIAL y §6 requiere confirmación humana trazable de significado y explicación. La variante paralela con cleaning cambia texto fuera del error marcado y no queda licenciada automáticamente; debe pasar por revisión trazada. No se afirma aprobación humana.
- **R3 — E025, resuelta en el JSON:** se aceptan simplest y most simple como superlativos válidos y se explica que no se combinan most y -est.
- **R5 — E034 y R6 — E037, resueltas en el JSON:** se aceptan Monday morning y Thursday morning sin preposición, además de las formas con on. Las formas con in siguen siendo errores; on next Monday no aparece en los casos.

**Sin bloqueos pendientes en estas cinco observaciones.** La salvedad separada de **E029** se conserva: es una omisión del punto final y cuenta como PUNCTUATION, no como evidencia aislada de gramática A2.

E013/E022 siguen siendo partitivas estructuralmente defectuosas sin determinante después de of; las alternativas con of the están bien licenciadas. E026/E032 mantienen duplicaciones de conectores inequívocas; E032 no penaliza by foot ni arrived in the station y no etiqueta un comma splice como error objetivo. E008 tiene una tarea que coincide con el cuidado del gato y la devolución de llaves.

La auditoría integral previa cubrió los 60 casos y pasó los checks mecánicos descritos arriba. En esta actualización final releí E020: los nuevos campos de alternativa y explicación no cambian IDs, spans, longitudes, controles ni corrected_text primario. SHA-256 final del JSON: el indicado al inicio. Esta es una auditoría editorial independiente, no un registro de puntuación humana conforme a la rúbrica.
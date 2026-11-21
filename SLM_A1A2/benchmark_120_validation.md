# Validación de preparación Writing A1/A2 — 2026-10-11

Cierre de ejecución posterior: se completaron1920+640 respuestas, tras ampliar40 casos a16 configuraciones. Ver documentation/results_phase2.md y manifests/execution_completion_audit_20261011.json. El contenido de preparación debajo es histórico y no el estado actual de aprobación.

Actualización posterior a la entrega: el usuario autorizó expresamente las matrices1920+80 y exigió documentación para titulación. La autorización está en manifests/main_execution_authorization_20261011.json. El informe siguiente conserva el estado de preparación al congelar, anterior a esa aprobación; las inferencias aún no han empezado al responder la pregunta previa. El acceso y la comparabilidad de Fase1 se documentan en benchmark_120/phase1_results_access_and_comparability.md.

**Estado: preparación completada; pendiente de aprobación expresa de ejecución.** El benchmark v1 está congelado con resolución editorial de IA vinculada a las fuentes finales e informes independientes. Readiness actual16/16. La revisión de IA no equivale a aprobación humana de inferencias.

Benchmark: benchmark_development_120_v1.json, SHA256 `07308427c02adcc056a8964d3e4da41615db4b7fc0101870e277097de46d59f9`.

## Casos y fuentes

120 casos: 60 A1 y 60 A2; cada nivel tiene 45 incorrectos y 15 controles. Los 135 drafts originales quedan intactos; A2_controls_016_030.json continúa excluido. La normalización separada no sustituye las fuentes revisadas.

150 instancias, 31 categorías conjuntas. Por nivel: 25×1, 12×2, 6×3, 2×4; global: 50/24/12/4. Bloqueos estructurales: 0; revisiones estructurales: 0.

| Nivel | Media palabras | Mediana | Rango |
|---|---|---|---|
| A1 | 29.73 | 27.5 | 23–45 |
| A2 | 46.63 | 46.5 | 35–59 |

| Categoría | Instancias |
|---|---|
| ARTICLE | 7 |
| BASIC_CONNECTOR | 6 |
| BASIC_FUTURE | 10 |
| BASIC_LEXICAL_CHOICE | 4 |
| BASIC_MODAL | 3 |
| BE_FORM | 6 |
| CAPITALIZATION | 7 |
| COMPARATIVE | 4 |
| CONTRACTION | 1 |
| COUNTABLE_UNCOUNTABLE | 4 |
| MUCH_MANY | 4 |
| NEGATION | 3 |
| OBJECT_PRONOUN | 5 |
| PAST_SIMPLE | 10 |
| POSSESSIVE | 4 |
| PREPOSITION_PLACE | 4 |
| PREPOSITION_TIME | 3 |
| PRESENT_CONTINUOUS | 4 |
| PRESENT_PERFECT | 2 |
| PRESENT_SIMPLE | 2 |
| PUNCTUATION | 5 |
| QUESTION_FORM | 8 |
| SINGULAR_PLURAL | 7 |
| SOME_ANY | 4 |
| SPELLING | 3 |
| SUBJECT_PRONOUN | 2 |
| SUBJECT_VERB_AGREEMENT | 8 |
| SUPERLATIVE | 3 |
| VERB_PATTERN | 5 |
| VERB_PREPOSITION | 6 |
| WORD_ORDER | 6 |

Fuentes finales:
- A1_cases.json: `e2b7075b3db86d75a44f8a1accaa771359a7d44dd5ab4e570b470d7ccf56f50c`
- A2_cases.json: `ed40ec9181e340fb86e55f331cca98f2acb5b03f3bf4bda99b0b37340e811279`

Los dos informes independent_review_current cubren 60/60 IDs cada uno. review_resolutions_current.json liga sus hashes y las fuentes, registra los arreglos/alternativas y no declara aprobación humana. Se preservan variantes estándar y controles literales. Las correcciones recientes incluyen concordancia colectiva E001, alternativas posesivas/conectores/determinantes y variantes de tiempo/adverbio/superlativo/modal. E012 se diversificó y E040 se sustituyó por una regla de museo. A2-E029 solo acredita puntuación, no competencia gramatical A2 aislada.

El validador comprueba esquema, cuotas, longitudes, fragmentos únicos y no solapados, reconstrucción exacta del gold, controles y distribución. El prompt sigue literalmente el de Fase 1; user template: `Level: {level}\nTask: {task}\nStudent text: {student_text}`.

## Exclusión y límites de revisión

11940 comparaciones léxicas (7140 internas/4800 contra Fase 1); 0 candidatos sobre umbrales. Se revisaron además los veinte pares más cercanos. El detector no prueba ausencia de paráfrasis; la revisión manual de IA reparó una semejanza bajo umbral en E040. Ver benchmark_120/phase1_exclusion_review_current.md y strict_validation_120.json.
Fase 1 benchmark SHA256: `a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9`. Sus 24 artefactos siguen byte-idénticos; 23 blobs Git comprobados sin diferencias. No se modificaron enunciados ni resultados previos.

## Matriz y readiness

16 configs y 16 launchers: las 14 originales más LFM2.5-2.6B oficiales PTQ Q8_0/Q4_K_M (15/16, puertos 8115/8116). Se prepararon 1920 futuras inferencias de desarrollo y 80 futuras inferencias en una extensión aislada de los 40 casos. Ninguna está autorizada ni ejecutada.

20 activos locales volvieron a verificar tamaño/SHA y estabilidad contra upstream o el record de conversión; la junction referencia una sola copia. Qwen ya convertido, sin reconversión. Gemma conserva templates distintos: cinco renders offline texto/non-thinking iguales, conclusión limitada a esas pruebas. Todos los comandos usan localhost, contexto 4096, un slot, ngl 999, seed 42, sin mmproj/MTP/grammar; generación max_tokens 512 y parámetros por familia congelados.

Manifest SHA256 actual: `8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255`.
Readiness actual: **16/16 ready**, ligada exactamente al manifiesto actual, con complete_matrix=true. Todas las respuestas sintéticas tienen content no vacío, reasoning_content vacío y finish_reason=stop. Se midió CUDA y offload positivo de todas las capas registradas; el máximo device-wide de VRAM fue5398MiB (incluye otros procesos). No se bajó ngl ni se cambió muestreo/max_tokens tras observar salidas. Esta readiness prueba operación técnica y contrato non-thinking, no calidad lingüística ni ausencia de razonamiento interno.

Las 16 configuraciones mantienen --reasoning off y --reasoning-budget0; la API recibe reasoning_budget_tokens=0. Qwen/MiniCPM/Gemma pasan enable_thinking=false en sus kwargs nativos. LFM2.6 conserva su prefijo nativo abierto y usa el cierre forzado del sampler con presupuesto cero. No se reemplazó ninguna plantilla. Los renders nativos Gemma oficial/Unsloth coincidieron para la prueba técnica; sus templates tienen hashes distintos y esta observación finita no prueba equivalencia para toda entrada.

La autorización expresa «Autorizo esas cuatro repeticiones técnicas de readiness con thinking desactivado» quedó fijada por SHA en manifests/readiness_repeat_authorization_20261011.json. Se hicieron exactamente16 peticiones nuevas: una repetición para01–04 y primera prueba para05–16. Las cuatro anteriores permanecen byte-idénticas; total20 peticiones técnicas. Los claims exclusivos y permanentes impiden más generaciones, incluso tras resultado incierto. Una revisión independiente Luna6 max encontró0 bloqueos en ese control y volvió a pasar sus seis pruebas.

El primer intento adicional QwenF16 solo cargó/renderizó, con0 generaciones: el logger3 ocultaba la evidencia de offload. Se preservaron logs y se corrigió logger4 conforme al código antes de generar. La readiness anterior fallida MiniCPM permanece archivada bajo su SHA original; nunca se reatribuyó al manifiesto actual. Ver logs/readiness_before_nonthinking_update, manifests/nonthinking_runtime_verification_120.json y llama_cpp_readiness_report.json/.md.

## Código, controles y pendientes

Runner120 preparado con autorización+SHA, readiness completa vinculada, RAW fsync/reanudación, sin gold transmitido, una configuración cargada y rehash antes del spawn. Runner40 separado usa whitelist LFM26 y los 24 hashes de Fase1, con salida fija results_40_lfm26. La selección de parsed tras retry-failed se vincula a grupos de tentativas RAW autorizadas y selecciona la última, aunque haya fallado; se rechazan mezclas/duplicados ambiguos.

Suite completa de fixtures/mocks: 113 pruebas OK; no inferencias reales en los tests. Los resultados principales raw/parsed están vacíos; no se creó ni consultó el test final. Código/diagnósticos se conservan en Git local sin remoto.

Limitación de procedencia Qwen: el record no fija SHA histórico del cuantizador usado; el binario actual coincide con runtime hashes. No se inventó una identidad histórica ni se reconvirtió. Los renders finitos no demuestran equivalencia lógica total de templates. Ver runtime_resolutions_current.json y asset_provenance_120.md.

Integración final comprobada sin iniciar servidores ni conceder autorización: contrato de120 casos,16 configuraciones, readiness ligada al SHA, validación ligada al benchmark congelado, prompts idénticos al canónico y extensión aislada40×2. El guard rechaza la ejecución sin autorización; RAW/parsed principales y de la extensión siguen vacíos. Ver manifests/preparation_integration_120.json.

Único paso pendiente: aprobación humana expresa de las1920 inferencias de desarrollo y de las80 inferencias LFM2.6 Q8_0/Q4_K_M sobre los40 casos conservados (pueden aprobarse por separado). «Continúa» no autoriza esas inferencias. El test final no se creó, abrió ni consultó.

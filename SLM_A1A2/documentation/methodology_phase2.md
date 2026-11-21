# Metodología experimental — Fase 2 Writing A1/A2

Este documento fija el diseño, la procedencia, la ejecución y el método de evaluación de la Fase 2 para el trabajo de titulación. Distingue los hechos de preparación y ejecución verificados de los resultados automáticos provisionales; la revisión humana de calidad lingüística sigue pendiente.

**Estado al 11 de octubre de 2026:** el benchmark de desarrollo está congelado y vinculado al SHA `07308427c02adcc056a8964d3e4da41615db4b7fc0101870e277097de46d59f9`; el manifiesto de 16 configuraciones está vinculado al SHA `8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255`. La autorización inicial cubrió 1.920 inferencias de desarrollo y 80 sobre los 40 casos históricos; la instrucción posterior amplió la segunda matriz a 640 antes de ejecutarla. Ambas matrices ya terminaron: 1920+640 respuestas nuevas. La ampliación 40×16 reemplazó la propuesta inicial40×2 antes de ejecutarla. Los resultados y límites están en results_phase2.md; los proxies estrictos requieren revisión humana de calidad lingüística. Las pruebas sintéticas de readiness son comprobaciones técnicas y no se cuentan como resultados del benchmark.

## Objetivo y alcance

El experimento mide cómo configuraciones locales de modelos de lenguaje realizan una tarea de detección y corrección de errores en textos de estudiantes de inglés en niveles A1 y A2. Cada respuesta debe respetar un esquema JSON que declare si el texto es correcto, entregue el texto corregido, enumere los errores y sus correcciones, explique los cambios y devuelva feedback. El diseño mide por separado detección, corrección, conservación de controles y cumplimiento del formato.

La Fase 2 contiene dos alcances:

| Alcance | Casos | Configuraciones | Llamadas previstas | Uso |
|---|---:|---:|---:|---|
| Desarrollo nuevo | 120 | 16 | 1.920 | Comparación principal de configuraciones y cuantizaciones |
| Prueba común de todas las configuraciones | 40 históricos | 16 | 640 | Mismo runtime y muestreo congelado, incluida LFM2.5-2.6B, en carpeta nueva |

El conjunto final de aproximadamente 200 casos no forma parte de esta etapa. El registro de autorización lo deja sin acceso (`final_test_access: false`), y no se ha creado ni consultado.

## Diseño del conjunto de desarrollo

El archivo congelado `benchmark_development_120_v1.json` contiene 120 casos nuevos: 60 de nivel A1 y 60 de A2. Cada nivel tiene 45 textos con errores intencionales y 15 controles correctos. En total hay 90 casos incorrectos, 30 controles y 150 errores anotados en 31 categorías. Entre los 90 casos incorrectos, 50 tienen un error, 24 tienen dos, 12 tienen tres y cuatro tienen cuatro. Los controles incluyen variantes estándar y formulaciones correctas que no deben editarse, como diferencias BrE/AmE y orden natural de adverbios.

Las longitudes objetivo son 15–60 palabras para A1 y 25–100 para A2. El contenido de usuario sigue la plantilla congelada `Level: {level}\nTask: {task}\nStudent text: {student_text}` y el system prompt se conserva igual al de la Fase 1. Las respuestas se piden en JSON mediante instrucciones de texto; el servidor no impone gramática ni decodificación restringida por JSON.

La autoría editorial se auditó antes de observar las respuestas de esta corrida. Los informes actuales cubren los 60 IDs de cada nivel, registran cero bloqueos y describen las correcciones editoriales incorporadas al archivo congelado. Son auditorías editoriales asistidas por IA; no equivalen a una validación humana ni a juicios humanos de las respuestas del benchmark.

Para reducir contaminación con la prueba anterior, se compararon textos por igualdad y similitud léxica. El informe registra 11.940 comparaciones (7.140 internas al conjunto de 120 y 4.800 contra Fase 1), cero candidatos sobre los umbrales y una revisión adicional de los 20 pares más cercanos. La revisión editorial diversificó un caso que se consideró parecido pese a quedar bajo el umbral. Esta pantalla no demuestra ausencia universal de paráfrasis semánticas.

## Modelos, fuentes y cuantizaciones

La selección reúne escalas de referencia de mayor precisión y cuantizaciones de cada familia cuando existen. Las comparaciones dentro de una familia son más informativas que las comparaciones entre familias, pero tampoco siempre aíslan un único factor: puede cambiar la procedencia del archivo, la receta de conversión o el formato fuente.

| Configuraciones | Fuente fijada | Formatos y observación metodológica |
|---|---|---|
| Qwen3.5-2B: F16, Q8_0, Q4_K_M | `Qwen/Qwen3.5-2B`, revisión `15852e8c16360a2fea060d615a32b45270f8a8fc`, Apache-2.0 | El checkpoint Transformers se convirtió localmente a GGUF F16; Q8_0 y Q4_K_M se generaron desde esa referencia F16. |
| Qwen3.5-4B: Q8_0, Q4_K_M | `Qwen/Qwen3.5-4B`, revisión `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, Apache-2.0 | El F16 convertido se conserva como intermedio, no como una configuración evaluada. No hay brazo F16 de 4B en la matriz. |
| MiniCPM5-2B: F16, Q8_0, Q4_K_M | `openbmb/MiniCPM5-2B-GGUF`, revisión `2079a22f3beaa4e306449978533478fe0522f4b3`, Apache-2.0 | Se usan los GGUF publicados que figuran en el inventario. No se atribuye una receta de cuantización que el registro de origen no demuestre. |
| LFM2.5-1.2B-Instruct: BF16, Q8_0, Q4_K_M | `LiquidAI/LFM2.5-1.2B-Instruct-GGUF`, revisión `8ed288026e23958ad9dfa92d53ed773a8eee7125`, `lfm1.0` | GGUF del repositorio fijado. El término BF16 identifica el formato de referencia del artefacto registrado. |
| Gemma 4 E2B: QAT Q4_0; Unsloth Dynamic UD-Q4_K_XL y UD-Q2_K_XL | `google/gemma-4-E2B-it-qat-q4_0-gguf`, revisión `675cff42a74c774d6cb76f76d8eacb49b48c9b93`; `unsloth/gemma-4-E2B-it-qat-GGUF`, revisión `66a399f68ddd113b06dff02fca9523e55465d11d`; Apache-2.0 según inventario | La variante Google Q4_0 es un artefacto QAT. Las variantes Unsloth son cuantizaciones dinámicas derivadas de un checkpoint etiquetado QAT; no se agrupan como cuantización Q4 uniforme ni se tratan como la misma fuente experimental. |
| LFM2.5-2.6B: Q8_0, Q4_K_M | `LiquidAI/LFM2.5-2.6B-GGUF`, revisión `e7caca5d835a3901a8e0d63e94009429bafafdfc`, `lfm1.0` | Dos GGUF oficiales PTQ, con hashes fijados. Son nuevas en ambos alcances; no hay baseline histórico de estos archivos. |

En el razonamiento local de cuantización, Q8_0 funciona como ancla de mayor precisión dentro de los GGUF evaluados; Q4_K_M es un punto de menor tamaño con asignación de formatos por tensor; Q4_0 y las variantes dinámicas de Gemma tienen procedencias diferentes. Estos nombres describen la representación de pesos, no una garantía de exactitud. Los detalles se apoyan en `manifests/quantization_rationale_120.md` y en las fuentes de llama.cpp fijadas allí; no se importan cifras de perplexity ni resultados de proveedores como si fueran mediciones propias.

La conversión de Qwen está trazada en `manifests/qwen_conversion_record_120.json`: revisión fuente, conversor, receta y hashes de salida. El registro no conserva un hash propio del ejecutable cuantizador en la fecha histórica de conversión. El hash del binario disponible hoy no prueba retrospectivamente cuál ejecutable se usó entonces; esa incertidumbre se mantiene explícita.

La matriz no permite afirmar que una diferencia de resultado entre dos filas se deba solo al número de bits. Las comparaciones entre arquitecturas cambian tamaño, entrenamiento, fuente y plantilla. Gemma combina QAT y Unsloth Dynamic; Qwen3.5-4B no tiene F16 en la matriz; y los GGUF de MiniCPM/LFM proceden de repositorios publicados. Estas diferencias limitan las atribuciones causales.

## Runtime y parámetros de generación

El runtime fijado es llama.cpp b11457, commit `5ad1c5da0ad7f6176256b823925aad19134f0263`, con el binario y los modelos ligados a sus hashes en el manifiesto. El entorno registrado es Windows x86_64, RTX 3070 de 8 GiB, driver 610.88 y 17,09 GB de RAM total. La medición de readiness anotó memoria de GPU a nivel del dispositivo completo; no se atribuye como consumo exclusivo de un modelo.

Se usa un servidor local a la vez, enlazado a `127.0.0.1`, una secuencia en paralelo, contexto 4.096, `-ngl 999` como intento de offload y plantilla nativa embebida en cada GGUF. `-ngl 999` es el valor solicitado al backend, no una afirmación de que todas las capas se ubicaron en GPU. No se habilitan proyector multimodal, MTP, speculative decoding ni gramática JSON. La evidencia de las plantillas es finita: los renders sintéticos coincidentes no prueban equivalencia para toda entrada.

Los 16 perfiles fijan `max_tokens=512`, `seed=42`, `reasoning_budget_tokens=0`, `frequency_penalty=0` y los valores de familia siguientes. Los parámetros completos y cualquier valor explícito de backend están en `manifests/experiment_manifest_120.json`.

| Familia | Temperature | top_p | top_k | min_p | repeat_penalty | presence_penalty | Parámetro de pensamiento |
|---|---:|---:|---:|---:|---:|---:|---|
| Qwen3.5 | 0,7 | 0,8 | 20 | 0 | 1,0 | 1,5 | `enable_thinking=false` |
| MiniCPM5 | 1,0 | 0,95 | 40 | 0 | 1,0 | 0 | `enable_thinking=false` |
| LFM2.5-1.2B | 0,1 | 0,95 | 50 | 0,05 | 1,05 | 0 | presupuesto de razonamiento 0 |
| Gemma 4 E2B | 1,0 | 0,95 | 64 | 0,05 | 1,0 | 0 | `enable_thinking=false` |
| LFM2.5-2.6B | 0,1 | 0,95 | 50 | 0,05 | 1,1 | 0 | presupuesto de razonamiento 0 |

Los valores recomendados por el proveedor se conservaron antes de observar resultados. En LFM2.5-2.6B, `top_p=0,95` y `min_p=0,05` son valores explícitos del backend, no recomendaciones del README fijado. Para MiniCPM se pasa `min_p=0` expresamente, dado que la nota local de procedencia advierte sobre el valor por defecto del backend. No se cambian parámetros en respuesta a una salida deficiente.

El modo de pensamiento se desactiva con `--reasoning off` y `--reasoning-budget 0`, además del campo `reasoning_budget_tokens=0` de la solicitud. Qwen, MiniCPM y Gemma reciben `enable_thinking=false` donde su plantilla lo soporta. LFM2.5-2.6B mantiene el prefijo de pensamiento de su plantilla nativa y el sampler b11457 fuerza el cierre inmediato con presupuesto cero. Esto controla la solicitud y la respuesta observable; no demuestra ausencia de cómputo interno.

## Protocolo de ejecución y trazabilidad

Antes de cada configuración, el runner comprueba la autorización ligada al SHA exacto del benchmark, la validación congelada, el manifiesto, la readiness de las 16 configuraciones y el hash estable del modelo. Un fallo en un gate detiene el proceso antes de cargar un modelo. Cada configuración se ejecuta secuencialmente sobre los mismos casos y prompts.

El runner carga el archivo completo y valida la presencia del gold en el contrato; no transmite gold al servidor. La petición usa únicamente el system prompt canónico y los campos level, task y student_text. Guarda cada intento RAW y lo sincroniza a disco antes de parsear la respuesta; el archivo RAW es la fuente de verdad para reanudar y reconstruir el checkpoint. Las salidas parseadas son derivadas. Se registran configuración, caso, intento, hashes, estado HTTP, contenido exacto, telemetría disponible y razón de parada. El runner no puntúa: la evaluación se hace en una etapa separada.

Los errores de transporte admiten hasta dos reintentos técnicos conforme al registro de inicio. No se vuelve a intentar por JSON inválido, truncamiento, repetición o calidad semántica. HTTP 429 detiene la corrida completa inmediatamente, sin reintento. Un límite de tasa del modelo de agente Luna6 Max también requiere dejar un traspaso preciso y detenerse, sin sustitución. Estas reglas conservan los intentos fallidos y evitan elegir una respuesta por calidad.

La prueba común de 40 casos utiliza run_benchmark_40_current.py y el benchmark histórico SHA a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9. La autorización adicional fija las dieciséis configuraciones del manifiesto sin modificarlo; la salida es results_40_current_16/. El preflight y el cierre verificaron los 24 artefactos originales. La propuesta LFM-only 80 quedó incluida sin ejecutarse por separado.

## Evaluación de respuestas

La rúbrica de `benchmark_120/evaluation_rubric_120.md` asigna a cada par modelo-caso un veredicto provisional `CORRECT`, `PARTIAL`, `INCORRECT` o `INVALID_CASE`. El esquema JSON se registra por separado de la calidad lingüística. El parser distingue JSON directo, JSON recuperable tras quitar cercas o extraer el objeto, y respuesta inválida; además registra cercas, texto fuera del objeto, errores de esquema y cumplimiento JSON estricto.

Para los 90 casos incorrectos se cuentan TP, FP y FN de forma estricta. Un TP exige que original coincida con el fragmento gold, que la corrección predicha coincida exactamente con una opción licenciada por el gold y que aparezca en el texto corregido. Cada predicción se usa como máximo una vez. Se calculan precision, recall y F0.5 con agregación micro. La similitud aproximada, sin distinguir mayúsculas o puntuación, es una pista de revisión y nunca un TP.

Los 30 controles tienen métricas propias: CTMR mide la proporción cuyo texto fue modificado; CFAR mide la proporción marcada como incorrecta o con errores declarados; también se informa qué controles quedaron íntegramente preservados. Por ello un modelo no puede compensar falsas alarmas en controles con buen recall en errores.

La semántica y las explicaciones requieren revisión humana explícita. Cada `CORRECT` provisional en un caso con errores queda marcado para revisión; el resultado humano debe incluir revisor, fundamento, conservación del significado y validez de explicaciones. Los registros sin trazabilidad no convierten una métrica provisional en confirmada. La rúbrica informa resultados por nivel, tipo de error, número de errores y longitud, además de formato y telemetría; no reduce la comparación a un único puntaje.

Si se detecta un caso defectuoso tras congelar el archivo, se marca `INVALID_CASE` para todos los modelos y se excluye de los agregados; el gold no se reescribe después de ver salidas. Duplicados RAW o IDs desconocidos hacen abortar la evaluación en lugar de escoger una respuesta.

## Resultados técnicos disponibles y resultados pendientes

La readiness vinculada al manifiesto actual pasó 16/16 configuraciones. En las 16 pruebas sintéticas finales, el contenido fue no vacío, `reasoning_content` quedó vacío y `finish_reason` fue `stop`. El registro suma 16 solicitudes técnicas nuevas y cuatro históricas conservadas, 20 en total. No se puntúan ni se incluyen en los denominadores de 1.920 y 80; tampoco validan la calidad lingüística de los modelos.

La autorización y el registro de inicio fijan el orden `development_120` y luego `lfm26_phase1_40`, los hashes de ambos benchmarks, el hash del manifiesto y de los dos runners, y confirman que sampling y gold no cambiaron. En el primer intento de lanzamiento desde la raíz del repositorio, el preflight falló por rutas relativas al directorio del laboratorio; no se inició servidor ni se hizo inferencia. Se corrigió solo el directorio de trabajo y se inició la sesión desde `SLM_A1A2`. El incidente cuenta como cero inferencias y no cambia el protocolo congelado.

Esta tabla resume los registros de cierre; los resultados completos están en results_phase2.md. Los conteos deben separar filas esperadas, RAW finales, fallos técnicos, reintentos técnicos, respuestas truncadas o inválidas, HTTP 429 si lo hubiera, y respuestas puntuables. Los resultados semánticos seguirán identificados como provisionales hasta la revisión humana trazable.

| Alcance | Llamadas esperadas | Llamadas completadas | Filas finales y fallos | Métricas provisionales | Estado humano |
|---|---:|---:|---|---|---|
| Desarrollo 120 × 16 | 1.920 | 1.920 | 0 fallos técnicos | Informes completos, proxies provisionales | 0 confirmaciones humanas |
| Prueba común 40 × 16 (incluye LFM2.5-2.6B) | 640 | 640 | 0 fallos técnicos | Informes completos, proxies provisionales | 0 confirmaciones humanas |

## Resultados históricos de la prueba de 40 casos

La consulta histórica se resuelve a partir del inventario de solo lectura `benchmark_120/phase1_results_access_and_comparability.md` y `manifests/phase1_results_access_audit_20261011.json`. La corrida inicial de Fase 1 conserva 269 pares únicos: seis modelos con 40/40 y MiniCPM5-2B con 29/40; no contiene Gemma. La corrida consolidada de repetición conserva 320 pares únicos: ocho modelos por los mismos 40 casos. Los ocho son LFM2.5-350M, LFM2.5-1.2B-Instruct, LFM2.5-1.2B-Thinking, Qwen3.5-0.8B, Qwen3.5-2B, MiniCPM5-1B, MiniCPM5-2B y Gemma 4 E2B QAT Mobile. Los informes de comparación originales siguen siendo la fuente de los puntajes históricos; esta metodología no los recalcula ni los combina con la Fase 2.

La tabla completa de métricas originales por modelo se documenta en [historical_phase1_results.md](historical_phase1_results.md). Ese documento mantiene la definición y procedencia de los resultados históricos separadas de la evaluación nueva.

El usuario aclaró que la corrida inicial se interrumpió porque el modo Thinking agotó el presupuesto de salida. El inventario técnico registra 512 como límite de generación en esa primera ejecución; la corrida consolidada registró 2.048, generación greedy (`do_sample=false`), sin seed fijada, contexto 4.096, Transformers 5.18.0 y torch 2.14.1+cu130. La fase actual usa llama.cpp, GGUF, seed 42, máximo 512 y política no-thinking. Estos cambios impiden interpretar diferencias entre fases como efecto aislado de una cuantización o arquitectura.

Una revisión documental reciente detectó una discrepancia en el conteo de casos históricos señalados para revisión: una frase narrativa dice seis, mientras el registro estructurado y el CSV enumeran cinco. Se conserva aquí la discrepancia y se usa cinco como conteo provisional del registro estructurado; no se agrega un sexto caso sin reconciliar el índice fuente. Los archivos históricos permanecen de solo lectura.

La correspondencia es parcial, no exacta: hay antecedentes de modelos o familias Qwen3.5-2B, MiniCPM5-2B, LFM2.5-1.2B y Gemma E2B, pero cambian backend, formato, artefacto o parámetros. Qwen3.5-4B y LFM2.5-2.6B no tienen resultado histórico en esos 40 casos; la extensión nueva de LFM2.5-2.6B se mantendrá separada.

## Límites de interpretación

El conjunto de 120 es de desarrollo y su selección no sustituye un test independiente. Las auditorías editoriales disponibles son evidencia de revisión del diseño, no aprobación humana. La similitud léxica no descarta toda paráfrasis; el matching exacto puede dejar alternativas gramaticales no enumeradas como parciales; y los juicios de significado/explicaciones quedan pendientes de personas revisoras con trazabilidad.

La revisión de diseño advierte que A2-E029 es un caso válido de puntuación cuyo único error es el punto final; no debe presentarse como evidencia aislada de competencia gramatical A2. Esta excepción queda en la taxonomía y se interpreta por su categoría, no como una omisión del informe.

El hardware compartido y el offload observado deben describirse con los logs de cada ejecución; el valor `-ngl 999` solo documenta el intento. La prueba sintética no predice la tasa de fallos de las 120 entradas. Los resultados entre fases no son un experimento pareado de cuantización, y los resultados entre arquitecturas no aíslan tamaño o formato. Cualquier conclusión de generalización requiere el test final en una fase posterior, bajo un protocolo ya congelado.

## Fuentes locales de reproducibilidad

- Autorización y límites: `manifests/main_execution_authorization_20261011.json` y `manifests/execution_start_record_20261011.json`.
- Benchmarks y hashes: `benchmark_120_validation.md`, `benchmark_120/strict_validation_120.json`, `benchmark_120/lfm26_scope_addendum.md`.
- Modelo y runtime: `manifests/experiment_manifest_120.json`, `manifests/model_inventory_120.json`, `manifests/asset_provenance_120.md`, `manifests/qwen_conversion_record_120.json` y `manifests/runtime_asset_hashes_120.json`.
- Quantización y pensamiento: `manifests/quantization_rationale_120.md`, `manifests/nonthinking_runtime_verification_120.json`, `manifests/native_template_comparison_120.md`.
- Ejecución y evaluación: `run_benchmark_120.py`, `run_benchmark_40_lfm26.py`, `scripts/evaluate_benchmark_120.py`, `benchmark_120/evaluation_rubric_120.md`.
- Contexto histórico y exclusión: `benchmark_120/phase1_results_access_and_comparability.md`, `manifests/phase1_results_access_audit_20261011.json`, `benchmark_120/phase1_exclusion_review_current.md`.
- Plan de trabajo local consultado: `C:\Users\Kevin\.commandcode\plans\phase2-writing-benchmark-preparation.md`.

## Ampliación autorizada durante la corrida

El usuario indicó que todos los modelos actuales deben tener resultados de los 40 casos, incluidos Qwen3.5-4B. La prueba nueva se amplió a40×16=640 pares, usando exactamente las dieciséis configuraciones congeladas. Se ejecutará después de120×16=1920; total2560 pares nuevos. La extensión LFM-only80 prevista inicialmente queda incluida en las640 y no se ejecutará por separado.

No se modificó el manifiesto de la corrida activa. La autorización adicional está en manifests/main_execution_expansion_20261011.json y su validación técnica en benchmark_40_archive/current16_extension_validation.json. El runner nuevo es run_benchmark_40_current.py y su salida fija results_40_current_16/. Los40 casos y todos los resultados históricos siguen protegidos por sus hashes.

Esta ampliación permite comparar las configuraciones actuales sobre un conjunto común con el mismo runtime y generación, además de conservar los antecedentes históricos. No convierte los 40 casos usados en desarrollo previo en un test final ni elimina las diferencias metodológicas con la corrida Transformers antigua.

## Cierre y alcance de la medición

Las 2560 respuestas se verificaron contra RAW y fingerprints del prompt; hubo0 reintentos. Se verificaron 24 artefactos y23 blobs históricos,11 activos runtime y32 logs CUDA/offload. La suite final pasó 138 tests de fixtures/mocks. El evaluador primario no se modificó después de la preparación; se corrigió solo la representación de conteos de formato observados en cero, distinguiéndolos de datos no recogidos.

El diagnóstico posterior de granularidad identifica limitaciones reales del proxy: un texto final puede coincidir con el gold aunque declaraciones válidas usen fragmentos cortos y no coincidan con los fragmentos de referencia. No cambia ninguna puntuación ni concede juicio humano. Está identificado como análisis posterior exploratorio en annotation_granularity_diagnostic.md y JSON/CSV por caso. Los resultados automáticos no deben llamarse calidad lingüística confirmada. La latencia de escritorio no fue aislada de actividad concurrente y VRAM es device-wide.

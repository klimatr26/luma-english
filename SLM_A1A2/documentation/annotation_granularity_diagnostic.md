# Diagnóstico posterior: fragmentos declarados y texto corregido

Este análisis descriptivo se realizó después de observar las respuestas. No cambia los puntajes primarios, el gold, la selección de tentativas ni los parámetros. No es revisión humana de semántica o explicaciones.

La rúbrica congelada exige coincidencia literal del fragmento original, corrección licenciada y realización en corrected_text. Esto penaliza declaraciones válidas con límites distintos: en Qwen3.5-4B Q8/A1-E001, el gold declara art teacher meet → art teacher meets y Lina bring → Lina brings; el modelo declara meet → meets y bring → brings. Las ediciones únicas y no solapadas reconstruyen exactamente el mismo texto primario, pero el proxy registra TP=0, FP=2, FN=2 e INCORRECT provisional. Es una limitación de la medición de declaraciones, no evidencia de que esas dos correcciones sean gramaticalmente erróneas.

Por ello los veredictos/F0.5 primarios son proxies de coincidencia estricta y no deben presentarse como exactitud lingüística validada. Coincidir con el texto primario tampoco valida las explicaciones, clasificación is_correct o variantes no previstas. Hace falta revisión trazada para resolver las discrepancias.

## Desarrollo: conteos descriptivos sobre 90 textos incorrectos por configuración

| Configuración | Texto primario idéntico /90 | Alternativa completa licenciada /90 | Primario idéntico pero no CORRECT estricto | Efecto de ediciones declaradas = primario /90 | Reconstrucción no verificable /90 |
|---|---:|---:|---:|---:|---:|
| 01-qwen35-2b-f16 | 37 | 1 | 32 | 28 | 4 |
| 02-qwen35-2b-q8-0 | 38 | 1 | 31 | 27 | 8 |
| 03-qwen35-2b-q4-k-m | 41 | 0 | 33 | 26 | 6 |
| 04-minicpm5-2b-f16 | 35 | 0 | 27 | 28 | 30 |
| 05-minicpm5-2b-q8-0 | 40 | 0 | 29 | 32 | 25 |
| 06-minicpm5-2b-q4-k-m | 44 | 1 | 35 | 35 | 4 |
| 07-lfm25-12b-bf16 | 54 | 0 | 54 | 10 | 6 |
| 08-lfm25-12b-q8-0 | 55 | 0 | 55 | 8 | 7 |
| 09-lfm25-12b-q4-k-m | 55 | 1 | 55 | 1 | 3 |
| 10-qwen35-4b-q8-0 | 62 | 1 | 43 | 57 | 4 |
| 11-qwen35-4b-q4-k-m | 61 | 2 | 42 | 55 | 6 |
| 12-gemma4-e2b-qat-q4-0 | 72 | 1 | 51 | 64 | 0 |
| 13-gemma4-e2b-ud-q4-k-xl | 70 | 1 | 54 | 62 | 7 |
| 14-gemma4-e2b-ud-q2-k-xl | 7 | 0 | 7 | 1 | 84 |
| 15-lfm25-26b-q8-0 | 53 | 2 | 45 | 40 | 11 |
| 16-lfm25-26b-q4-k-m | 57 | 1 | 54 | 39 | 13 |

Las ediciones se verifican mecánicamente solo cuando cada fragmento literal aparece exactamente una vez, no hay solapamiento y el resultado coincide tanto con corrected_text del modelo como con el gold primario. Un fragmento ambiguo, ausente, solapado o con forma inesperada queda no verificado; no se escoge una posición para favorecer una salida. Estos conteos no sustituyen ninguna métrica primaria.

Las huellas, ejemplos mecánicos y trazabilidad por caso están en results_120/reports/annotation_granularity_diagnostic.json y annotation_granularity_cases.csv. La prueba nueva de 40 casos se cerró con640 filas; sus diagnósticos están en results_40_current_16/reports/.

## Prueba común de 40: diagnóstico sobre 30 incorrectos por configuración

| Configuración | Primario idéntico /30 | Alternativa licenciada /30 | Primario idéntico pero no C estricto | Efecto de ediciones=primario /30 | No verificable /30 |
|---|---:|---:|---:|---:|---:|
| 01-qwen35-2b-f16 | 13 | 0 | 12 | 8 | 1 |
| 02-qwen35-2b-q8-0 | 9 | 0 | 8 | 6 | 6 |
| 03-qwen35-2b-q4-k-m | 10 | 0 | 10 | 9 | 3 |
| 04-minicpm5-2b-f16 | 15 | 1 | 13 | 10 | 8 |
| 05-minicpm5-2b-q8-0 | 16 | 1 | 13 | 11 | 6 |
| 06-minicpm5-2b-q4-k-m | 19 | 0 | 17 | 12 | 1 |
| 07-lfm25-12b-bf16 | 16 | 0 | 16 | 3 | 2 |
| 08-lfm25-12b-q8-0 | 16 | 0 | 16 | 3 | 3 |
| 09-lfm25-12b-q4-k-m | 16 | 0 | 16 | 1 | 0 |
| 10-qwen35-4b-q8-0 | 22 | 0 | 14 | 17 | 4 |
| 11-qwen35-4b-q4-k-m | 21 | 0 | 13 | 19 | 4 |
| 12-gemma4-e2b-qat-q4-0 | 21 | 0 | 18 | 19 | 3 |
| 13-gemma4-e2b-ud-q4-k-xl | 26 | 1 | 20 | 24 | 0 |
| 14-gemma4-e2b-ud-q2-k-xl | 3 | 0 | 3 | 1 | 28 |
| 15-lfm25-26b-q8-0 | 17 | 0 | 16 | 14 | 2 |
| 16-lfm25-26b-q4-k-m | 17 | 0 | 17 | 14 | 3 |

Una brecha entre primario idéntico y C estricto puede deberse también a flag, declaraciones o esquema; no se atribuyen todas las brechas a límites de fragmento. Todos los conteos son descriptivos posteriores, no aprobación humana ni reemplazo de la rúbrica primaria.

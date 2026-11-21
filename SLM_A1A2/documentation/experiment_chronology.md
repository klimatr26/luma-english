# Cronología experimental — Fase 2 Writing A1/A2

Registro de decisiones y cambios que afectan la reproducibilidad. Las fechas de Git se muestran en la zona local `America/Guayaquil` (UTC−05:00); el registro de inicio está en UTC. Los eventos de ejecución incluyen solo información ya asentada. Los conteos finales y la telemetría se cotejaron al cierre; los resultados automáticos siguen provisionales y la calidad lingüística requiere revisión humana.

## Preparación y congelación

| Fecha y hora local | Evento | Evidencia y efecto |
|---|---|---|
| 2026-10-06 21:36 | Se conserva la base de traspaso y se inicializa el control local (`f2eb39e`). | Se preserva la separación de Fase 1 y el plan inicial de un benchmark de desarrollo de 120 casos. El plan original preveía 14 configuraciones; luego se amplió con trazabilidad a 16. |
| 2026-10-11 03:00:07 | Se incorpora la matriz de 16 configuraciones y el runner aislado para la extensión de Fase 1 (`f88eaf7`). | Se fijan manifiesto, launchers, runtime, fuentes y parámetros. LFM2.5-2.6B Q8_0 y Q4_K_M se agregan tanto al desarrollo de 120 como a una extensión separada de 40 casos. |
| 2026-10-11 03:00:52 | Se preservan los casos revisados y el traspaso de readiness (`f192e4a`). | Se conservan los originales revisados A1/A2, las auditorías y el gate que impide inferir sin la readiness y la autorización vinculadas por SHA. |
| 2026-10-11 03:29:29 | Se fija la política sin pensamiento (`d28b99c`). | Todos los comandos declaran `--reasoning off` y presupuesto cero. Qwen, MiniCPM y Gemma pasan `enable_thinking=false` cuando la plantilla lo permite; las plantillas nativas no se sustituyen. |
| 2026-10-11 12:01:17 | Se concluye la readiness autorizada y se congela el benchmark de desarrollo (`179bb78`). | La readiness pasa 16/16; la verificación ligada al manifiesto informa contenido no vacío, `reasoning_content` vacío y `finish_reason=stop` para las 16 respuestas sintéticas. Se conservan los cuatro probes históricos y se documentan 16 nuevas peticiones técnicas, 20 en total. No son salidas evaluables del benchmark. |
| 2026-10-11 12:13:12 | Se registra el acceso histórico y la autorización expresa para ejecutar (`f8528cd`). | Quedan fijados el SHA del benchmark de 120, el SHA de los 40 casos históricos, el SHA del manifiesto, la lista de 16 configuraciones y las 1.920 + 80 llamadas previstas. Se concluye que el test final no está autorizado. |

El protocolo de parámetros, fuentes, revisión editorial y puntuación está desarrollado en [methodology_phase2.md](methodology_phase2.md). El plan local de preparación consultado está en `C:\Users\Kevin\.commandcode\plans\phase2-writing-benchmark-preparation.md`.

## Contexto histórico de Fase 1

La fecha exacta de las corridas previas de 40 casos no queda establecida en el inventario actual; por eso se documenta su orden, alcance y parámetros sin asignar una hora no registrada.

| Registro histórico | Filas/modelo-caso | Estado conocido |
|---|---:|---|
| Corrida inicial interrumpida | 269 únicas | Seis modelos completaron 40/40; MiniCPM5-2B quedó en 29/40; Gemma no aparece. El usuario aclaró que Thinking agotó el presupuesto de salida. El inventario técnico registra máximo de 512 tokens. |
| Corrida consolidada | 320 únicas | Ocho modelos completaron los mismos 40 casos; máximo 2.048 tokens, `do_sample=false`, sin seed fijada, contexto 4.096, Transformers 5.18.0 y torch 2.14.1+cu130. |

Los RAW y resultados existentes de Fase 1 se mantienen en sus ubicaciones históricas y no se mezclan con las nuevas llamadas. Una revisión posterior detectó que la nota narrativa cuenta seis juicios históricos pendientes de revisión mientras el registro estructurado y el CSV enumeran cinco. La discrepancia queda explícita y se adopta cinco solo como conteo provisional del registro estructurado; debe reconciliarse antes de convertirlo en una afirmación final de tesis. El informe de comparación original conserva los valores históricos y no se reevalúa en esta cronología.

La tabla de las métricas originales para los ocho modelos consolidados está en [historical_phase1_results.md](historical_phase1_results.md).

## Autorización y comienzo de ejecución

El usuario autorizó ambas matrices y pidió documentar los resultados anteriores. El registro inmutable `manifests/execution_start_record_20261011.json` marca el inicio a `2026-10-11T17:16:28.349736Z` (12:16:28, hora local), fija los hashes y el orden `development_120` seguido de `lfm26_phase1_40`, registra un máximo de dos reintentos técnicos y establece que HTTP 429 detiene el trabajo sin reintento. También registra `sampling_changed: false`, `gold_changed: false` y `final_test_access: false`.

El primer lanzamiento desde la raíz del repositorio fue rechazado por el gate antes de iniciar un servidor, porque las rutas del manifiesto son relativas al directorio `SLM_A1A2`. Se corrigió únicamente el directorio de trabajo y se volvió a iniciar desde el laboratorio. El intento rechazado produjo **cero inferencias**; no se modificaron prompts, argumentos, parámetros, modelos, gold ni archivos congelados. El registro `manifests/execution_start_record_20261011.json` conserva los SHA del runner, los benchmarks, el manifiesto y la readiness. La sesión de desarrollo terminó con 1920 respuestas y luego se ejecutó la ampliación común de 640.

## Resultados de ejecución: sección para completar al cierre

Los registros finales y results_phase2.md documentan por alcance:

- hora local de inicio/cierre y versión/hash del runner utilizado;
- llamadas esperadas y filas finales por configuración, separando éxito, error HTTP/transporte, truncamiento y respuesta no parseable;
- número y razón de reintentos técnicos; respuesta HTTP 429 si ocurrió y punto exacto de detención;
- tiempos y telemetría observada, indicando valores nulos o límites de atribución;
- resultados automáticos provisionales, denominadores y casos inválidos si existieran;
- número de juicios humanos trazables y estado de las explicaciones y conservación de significado;
- estado de la extensión LFM2.5-2.6B y verificación de que los 24 artefactos históricos protegidos siguieron intactos.

| Alcance | SHA de datos | Filas esperadas | Conteo al cierre | Estado de evaluación |
|---|---|---:|---|---|
| Desarrollo 120 × 16 | `07308427c02adcc056a8964d3e4da41615db4b7fc0101870e277097de46d59f9` | 1.920 | 1.920 verificadas | Completa, proxies provisionales |
| Prueba histórica común 40 × 16 | `a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9` | 640 | 640 verificadas | Completa, proxies provisionales |

Los conteos proceden de RAW, checkpoint y evaluador verificados, no de la readiness.

## Referencias de control

- Autorización: `manifests/main_execution_authorization_20261011.json`.
- Inicio de la corrida: `manifests/execution_start_record_20261011.json`.
- Readiness: `manifests/nonthinking_runtime_verification_120.json`, `llama_cpp_readiness_report.json`.
- Resultados históricos inventariados: `manifests/phase1_results_access_audit_20261011.json`, `benchmark_120/phase1_results_access_and_comparability.md`.
- Secuencia de preparación: commits locales `f2eb39e`, `f88eaf7`, `f192e4a`, `d28b99c`, `179bb78` y `f8528cd`.

## Ampliación autorizada durante la corrida

El usuario indicó que todos los modelos actuales deben tener resultados de los 40 casos, incluidos Qwen3.5-4B. La prueba nueva se amplió a40×16=640 pares, usando exactamente las dieciséis configuraciones congeladas. Se ejecutará después de120×16=1920; total2560 pares nuevos. La extensión LFM-only80 prevista inicialmente queda incluida en las640 y no se ejecutará por separado.

No se modificó el manifiesto de la corrida activa. La autorización adicional está en manifests/main_execution_expansion_20261011.json y su validación técnica en benchmark_40_archive/current16_extension_validation.json. El runner nuevo es run_benchmark_40_current.py y su salida fija results_40_current_16/. Los40 casos y todos los resultados históricos siguen protegidos por sus hashes.

Esta ampliación permite comparar las configuraciones actuales sobre un conjunto común con el mismo runtime y generación, además de conservar los antecedentes históricos. No convierte los 40 casos usados en desarrollo previo en un test final ni elimina las diferencias metodológicas con la corrida Transformers antigua.

## Cierre verificado del 11 de octubre de 2026

- Desarrollo:17:16:40–18:24:11 UTC,1920/1920 respuestas.
- Prueba común40×16:18:25:00–18:50:03 UTC,640/640 respuestas; sustituyó la extensión80 no iniciada.
-0 fallos de transporte,0 reintentos,0 filas faltantes;32 logs CUDA/offload y2560 fingerprints cotejados. Reasoning_content no vacío:0. Todos los puertos liberados.
- Evaluaciones primarias completas y provisionales;0 confirmaciones humanas. El análisis posterior de granularidad conserva los puntajes y se separa del protocolo previo.
-138 tests OK;24 artefactos y23 blobs Fase1 sin cambios;11 hashes runtime verificados. Test final sin crear ni consultar.

Ver results_phase2.md y manifests/execution_completion_audit_20261011.json. La revisión humana de calidad permanece pendiente; la colección y los informes de ejecución ya están cerrados.

## Comparación autorizada de finalistas — 17 de noviembre de 2026

Se redactaron y revisaron de forma cruzada por IA 200 textos nuevos (100 A1/100 A2, 150 incorrectos/50 controles, 248 errores intencionales), con resoluciones editoriales y hashes finales. El commit local `1b58599` congeló datos, prompts, muestreo, código evaluador y runtime antes de la primera respuesta. No hubo validación humana del gold.

Se compararon Gemma E2B UD-Q4_K_XL y Qwen3.5 4B Q4_K_M descargable de Unsloth, cada uno en CPU y Vulkan con el puente de la app b12359. La ejecución inicial sufrió una discrepancia de codificación de stdout de Python en Windows. Sus 31 respuestas completas y un fallo técnico permanecen archivados byte-idénticos. El commit `aa02cff` registra el lanzador UTF-8 y la incidencia; se reinició la matriz completa con el mismo manifiesto y sin cambios guiados por calidad.

La matriz principal se completó de 19:52 a 22:22 UTC (14:52–17:22 UTC−5): 800 respuestas, cero fallos técnicos y una tentativa por combinación caso/modelo/backend. Las tres salidas Gemma que alcanzaron el límite se conservaron y resultaron JSON incompleto. Se documentan aparte 32 intentos del bloque interrumpido y 13 generaciones sintéticas de preparación/calentamiento: 845 solicitudes locales de generación en total, 800 puntuadas.

Se aplicó ERRANT v2 y el mismo parser C# de la aplicación, con verificación de fuentes y 2.000 remuestreos pareados. Qwen obtuvo mayor corrección textual y menos falsas alarmas; Gemma tuvo menor latencia y RSS, y modificó menos controles. El resultado automático no certifica las explicaciones. La auditoría independiente por IA verificó las 800 filas contra RAW y no encontró bloqueos; los 24 artefactos históricos siguen byte-idénticos.

Ver [resultados y recomendación](finalists_200_results_20261117.md), [incidencia técnica](finalists_200_execution_20261117.md), [registro de ejecución](../results_finalists_200_v1/reports/execution_facts.json) y [muestra sin puntuar para revisión del investigador](../results_finalists_200_v1/reports/researcher_review_sample.json). No se agregan las observaciones de CPU y Vulkan como 400 textos independientes por modelo ni se atribuyen diferencias frente a 120 únicamente al prompting o a los pesos.

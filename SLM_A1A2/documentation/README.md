# Expediente experimental Writing A1/A2 para titulación

Este expediente conserva el diseño, la justificación, la ejecución y los resultados de las fases exploratoria, de desarrollo y de comparación de finalistas. Los resultados históricos permanecen en sus archivos originales; los informes nuevos identifican sus fuentes y límites de comparación. El 17 de noviembre se autorizó y completó una comparación nueva de 200 textos en dos modelos y dos backends. Su uso para elegir una configuración de producto se distingue de una confirmación independiente posterior de ese ganador.

## Documentos principales

1. [Resultados históricos de 40 casos](historical_phase1_results.md): ocho modelos, 320 respuestas consolidadas y la corrida inicial interrumpida de 269 respuestas. Incluye parámetros, revisiones, hashes y la incidencia de thinking que agotaba el presupuesto de salida.
2. [Metodología de Fase 2](methodology_phase2.md): diseño de 120 casos, selección de 16 configuraciones, cuantizaciones, procedencia, controles, thinking desactivado, protocolo de ejecución y rúbrica de evaluación.
3. [Cronología experimental](experiment_chronology.md): preparación, reparaciones editoriales, readiness, autorización e incidencias técnicas.

Las matrices autorizadas son 120×16 (1920 pares) y una nueva prueba de 40×16 (640 pares) de todas las configuraciones actuales. Ambas matrices están completas: 2560 respuestas recibidas con 0 fallos de transporte y0 reintentos. El cierre cotejó todos los RAW, prompts y hashes. La calidad lingüística permanece provisional hasta revisión humana trazada.

## Trazabilidad

- Benchmark de desarrollo: `../benchmark_development_120_v1.json`; validación: `../benchmark_120_validation.md`.
- Manifiesto: `../manifests/experiment_manifest_120.json`; justificación: `../manifests/quantization_rationale_120.md`.
- Autorización: `../manifests/main_execution_authorization_20261011.json`; inicio: `../manifests/execution_start_record_20261011.json`.
- RAW nuevos: `../results_120/raw/` y `../results_40_current_16/raw/`. Se conservan localmente y quedan fuera de Git; sus huellas se indexarán con los informes.
- Resultados históricos protegidos: `../benchmark_results_v2/`, `../benchmark_results_v2_rerun/` y `../benchmark_40_archive/phase1_baseline_hashes.json`.

Los resultados nuevos son métricas automáticas provisionales de coincidencia estricta. La conservación de significado y la corrección de las explicaciones requieren revisión humana trazable. Los puntajes históricos mantienen su rúbrica original y no se mezclan con los nuevos para atribuir efectos causales de cuantización o backend.

La ampliación 40×16 está autorizada en `../manifests/main_execution_expansion_20261011.json`; incluye las80 observaciones LFM2.5-2.6B previstas, sin duplicarlas. El runner `../run_benchmark_40_current.py` preserva el benchmark40, los resultados históricos y el manifiesto de120.

4. [Resultados y cierre experimental](results_phase2.md): tablas de las32 configuraciones-conjunto, formato, controles, telemetría, limitaciones y comandos de reproducción de los informes.
5. [Diagnóstico de granularidad de anotaciones](annotation_granularity_diagnostic.md): diferencias entre texto corregido y proxies de coincidencia de fragmentos, sin cambiar los puntajes primarios.
6. [Correspondencia con el plan aprobado y próximos pasos](plan_alignment_20261011.md): objetivos y cronograma del tutor frente a la evidencia real; correcciones de medición, evaluación humana, prompting, robustez y propuesta de trabajo hasta la entrega.
7. [Evaluación v2, preselección y fichas humanas](evaluation_v2_results_and_candidates.md): reprocesamiento de las 2.560 respuestas con ERRANT, cobertura y controles separados, tres candidatos provisionales y 180 fichas ciegas sin notas humanas.

La evaluación v2 es posterior y separada de la evaluación original. Su [protocolo](evaluation_v2_protocol.md), [integración ERRANT](errant_integration_v2.md) y [rúbrica humana](human_review_rubric_v2.md) describen las definiciones y límites. Los datos y puntajes originales permanecen intactos; los registros humanos futuros se importan por la interfaz v2 y se conservan en una capa independiente.

La documentación histórica contiene los ocho resultados originales y la corrida interrumpida. Las matrices y fuentes nuevas se conservan en results_120/ y results_40_current_16/, con CSV, JSON, evaluaciones por caso e índices SHA. Los RAW siguen locales fuera de Git; no existe remoto ni publicación externa.

8. [Página interactiva de revisión humana](human_review_web.md): instrumento local sin conexión con 180 fichas ciegas, asignación de 45 para segunda revisión, guardado de borradores, respaldos y exportación compatible con la importación v2. [Instrucciones para el evaluador](../review_web/LEEME.md).

9. [Prototipo local de Writing y revisión del investigador](local_demo_20261016.md): aplicación C#/Windows Forms, modelos y cuantizaciones, demostración interactiva del JSON y registro de la indicación del tutor sobre la revisión propia. [Guía del prototipo](../demo/README.md).

10. [Revisión humana aclarada e importada](human_review_results_clarified_20261109.md): cierre de 180 fichas con ocho aclaraciones confirmadas por el investigador, notas por criterio y trazabilidad. Se conservan como historial el [ingreso provisional](human_review_results_20261109.md) y las [fichas que requirieron aclaración](human_review_cases_pending_20261109.md).
11. [Seguimiento y versión de prompts](human_review_prompt_followup_20261109.md): integración de las observaciones y de recomendaciones opcionales, sin alterar resultados históricos ni atribuir mejoras sin probarlas.
12. [Viabilidad de Vulkan y Android](vulkan_android_feasibility_20261109.md): fuentes upstream, tamaños observados, arquitectura y comprobaciones pendientes.
13. [Integración Vulkan en Windows Forms](vulkan_windows_integration_20261109.md): runtime verificado, selección Auto Vulkan/CPU, pruebas sintéticas, incidencias y límites. [Notas de implementación y ruta Android](vulkan_android_integration_notes_20261109.md).
14. [Prototipo Avalonia para Windows y Android](../cross_demo/README.md): selección por capacidad con override, descargas verificadas, motor nativo local, reintentos de formato trazados y exportación. [Implementación, pruebas e incidencias](../cross_demo/docs/implementation_and_validation_20261109.md).
15. [Corrección de carga Android y prueba física](../cross_demo/docs/android_phone_load_fix_20261109.md): diferencia entre loader y GPU Vulkan, cierre nativo observado, preflight y alternativa CPU verificada en el teléfono, APK0.1.1 y trazabilidad de pruebas.
16. [Descargas móviles, rendimiento ARM y JSON guiado](../cross_demo/docs/mobile_downloads_and_runtime_20261109.md): versión0.1.2, NetworkOnMainThreadException, descarga con pantalla apagada, recuperación del trabajo del sistema, mediciones CPU y política de salida JSON separada del benchmark.
17. [LFM3-1.7B en las 40 preguntas](lfm3_17b_phase1_20261117.md). Compara las dos cuantizaciones con MiniCPM5 y LFM2.5 mediante ERRANT, el parser de Avalonia y mediciones de inferencia CUDA.
18. [Selección medida de CPU/Vulkan en Android](../cross_demo/docs/android_measured_backend_20261117.md): Mesa Turnip dentro de la app, cinco configuraciones Q4, política de calibración y APK 0.1.5 verificado en el F8 Pro.
19. [Gemma y Qwen en 200 preguntas nuevas](finalists_200_results_20261117.md): 800 respuestas de las configuraciones Q4 de producto, corrección textual, coherencia, controles, CPU/Vulkan y memoria. [Protocolo prospectivo](finalists_200_protocol_20261117.md), [validación de datos](../benchmark_200/validation.md) y [auditoría independiente por IA](../results_finalists_200_v1/reports/independent_result_audit.md).
20. [Incidencia UTF-8 y reinicio documentado](finalists_200_execution_20261117.md): conservación de 31 respuestas y un fallo técnico del intento incompleto; matriz completa reiniciada sin cambiar casos, prompts, parámetros ni binarios. [Muestra de 20 casos para revisión del investigador, sin notas](../results_finalists_200_v1/reports/researcher_review_sample.json).

# Integración del portátil y decisiones de despliegue

18 de noviembre de 2026, hora de Ecuador continental. Revisión de la copia entregada en `I:\Titulación\IA`, integrada en el proyecto del escritorio. No se ejecutaron inferencias nuevas durante esta integración.

## Qué se incorporó y cómo se comprobó

Ambos repositorios partían del commit local `d3cddc3`. Los **595 archivos versionados eran byte-idénticos**. También coincidían los dos documentos del curso y el traspaso del portátil que ya estaban sin commit. Se conservaron esos archivos; no se trasladó `.git`, no se configuró remoto y no se copiaron los modelos o las carpetas de herramientas.

Se incorporaron **161 archivos, 62 374 252 bytes**, con copia que rechaza conflictos y verificación SHA-256 de origen y destino. Comprenden cinco conjuntos de evidencia, cuatro runners, dos documentos y siete DLL del runtime experimental aislado. Las DLL de la aplicación siguen siendo las congeladas. El [inventario de importación](../manifests/laptop_integration_import_20261118.json) conserva rutas, tamaños, hashes y el estado base comparado.

Evidencia original incorporada, sin reescribir informes ni resultados:

- [CPU y Vulkan completo](../results_laptop_resources_v1/report.md), incluido el segundo intento técnico de Qwen que también falló antes del calentamiento.
- [Diagnóstico de la transferencia de pesos](../results_laptop_qwen_vulkan_diagnostic_v1/report.md): cinco sondas sintéticas, con fuentes C++ y registros.
- [Qwen híbrido y GPU Intel](../results_laptop_hybrid_gpu_v1/report.md).
- [Medición en batería](../results_laptop_battery_v1/report.md).
- [Presupuesto simulado de 2 GiB](../results_laptop_vram2g_v1/report.md).

La auditoría independiente de esta integración no importa ni ejecuta runners. Reconstruye la selección desde los 120 casos; verifica el subconjunto, identidades, orden, un intento por caso, SHA de prompts/modelos declarados y vínculos RAW/telemetría; recomputa estadísticas de latencia, throughput y picos de memoria y las coteja con CSV y cierres. Contrasta también código, protocolos, DLL y referencias congeladas. [Código de auditoría](../scripts/audit_laptop_results.py) · [Resultado de auditoría](../manifests/laptop_integration_audit_20261118.json).

Se verificaron **165 respuestas de recursos**, sobre **15 únicos textos de desarrollo** repetidos entre configuraciones y sesiones; son once bloques completos. No son 165 preguntas independientes ni nuevos resultados de precisión. Los 24 artefactos protegidos de Fase 1 permanecen byte-idénticos. Los 27 vínculos de código/runtime de la comparación de escritorio y el benchmark de 200 conservan sus SHA. Los dos GGUF de la copia del portátil se verificaron nuevamente por lectura y SHA, sin duplicarlos: [registro de pesos](../manifests/laptop_models_reverified_20261118.json).

Para repetir únicamente la auditoría desde la raíz:

```powershell
.\SLM_A1A2\.venv\Scripts\python.exe SLM_A1A2/scripts/audit_laptop_results.py
```

## Resultados de recursos que cambian la decisión

HP ZBook Studio x360 G5, Core i9-8950HK de 6 núcleos/12 hilos, 35,81 GiB de RAM detectada, Windows 11 Pro. Quadro P1000 de 4096 MiB, controlador 582.53; Intel UHD 630 integrada, controlador 31.0.101.2141. Mismos quince textos y perfiles de escritura: contexto 2048, máximo 512 tokens, thinking desactivado, semilla 42 y gramática JSON. Estos son perfiles completos por familia, no un aislamiento del efecto de los pesos.

| Configuración | Capas GPU | Mediana con corriente (s) | Mediana en batería (s) | Pico VRAM Quadro con corriente (MiB) | RSS pico con corriente (GiB) |
|---|---:|---:|---:|---:|---:|
| Gemma / CPU | 0 | 37,20 | 33,59 | 0 | 2,68 |
| Qwen / CPU | 0 | 84,13 | 74,87 | 0 | 4,15 |
| Gemma / Quadro | 36/36 | 8,88 | 9,63 | 1831 | 1,81 |
| Qwen / Quadro híbrido | 32/33 | 23,22 | 25,37 | 3165 | 3,33 |
| Gemma / Quadro, presupuesto simulado | 18/36 | 17,90 | — | 1347 | 1,79 |
| Qwen / Quadro, presupuesto simulado | 14/33 | 46,12 | — | 1920 | 3,32 |
| Gemma / Intel UHD 630 | 36/36 | 45,48 | — | No aplicable | 3,67 |

Cada celda de latencia observada resume 15 respuestas completas. Qwen con descarga completa en la Quadro falló al cargar, tanto en el intento principal como en la comprobación técnica. Qwen en Intel cargó 33/33 capas, pero el calentamiento agotó 120 segundos: **no se enviaron los quince casos** y no hay mediana de inferencia que asignarle. Los CSV originales incluyen prefill, decode, longitudes, velocidades y memoria privada; el [CSV conjunto](../results_laptop_integration_v1/comparison.csv) conserva el origen de cada fila.

Comparando por los mismos IDs con corriente, las medianas de los cocientes CPU/GPU fueron **3,59× para Qwen a 32/33**, **4,73× para Gemma a 36/36**, **1,82× para Qwen a 14/33** y **2,06× para Gemma a 18/36**. Las cuatro configuraciones de la Quadro ganaron a su CPU en los 15 pares. Estas razones pareadas no se calculan dividiendo las dos medianas de bloque.

El reparto parcial conserva una opción Qwen útil sin exigir que todos sus bloques estén en GPU. Aun así, Qwen a 14 capas (46,12 s) tardó más que Gemma en CPU (37,20 s) en las sesiones observadas; «GPU funciona» por sí solo no decide qué modelo conviene por defecto. La ventaja de precisión de Qwen procede de la [evaluación de 200](finalists_200_results_20261117.md), no de estas mediciones de recursos.

## Memoria: conclusiones respaldadas y límites

**4 GiB es una pista inicial útil para Qwen, no un mínimo universal ni garantía de carga.** El equipo físico tenía 4 GiB y presupuesto libre anunciado de 3617 MiB. La carga completa perdió el dispositivo durante la transferencia; dejar aproximadamente 70,33 MiB de pesos en CPU permitió continuar y generar. El diagnóstico logró ese resultado con dos colocaciones distintas. El pico global de 3165 MiB de la ejecución híbrida incluye contexto y cómputo. El error durante la carga completa ocurrió en otra fase y no demuestra agotamiento de toda la VRAM.

`VK_ERROR_DEVICE_LOST` admite varias causas; no debe clasificarse automáticamente como falta de memoria. Después de ese error hay que retirar el worker y crear un dispositivo lógico nuevo para un intento posterior. [Especificación Vulkan](https://docs.vulkan.org/spec/latest/chapters/devsandqueues.html#devsandqueues-lost-device).

**La prueba de 2 GiB es una simulación de presupuesto, no una GPU física de 2 GiB.** Se limitó la colocación y se comprobaron picos globales muestreados; no se redujo por hardware el heap a 2 GiB. La tarjeta conservó su cómputo, ancho de banda, controlador y capacidad física. Qwen quedó con 128 MiB de margen respecto del presupuesto simulado, un resultado demasiado ajustado para convertirlo en margen universal de producto. Pueden existir transitorios entre muestras.

**Conviene distinguir residencia, memoria compartida y arquitectura UMA.** En una GPU discreta, evitar superar su presupuesto local puede prevenir paginación y pausas; Windows expone presupuesto y uso por proceso mediante [QueryVideoMemoryInfo](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_4/nf-dxgi1_4-idxgiadapter3-queryvideomemoryinfo). La elección de un reparto explícito CPU/GPU es una estrategia razonable, que debe medirse. En estas pruebas no hay trazas de residencia o fallos de página que demuestren que un derrame de la Quadro a RAM compartida causó la lentitud.

En una integrada, reservar más RAM no crea por sí mismo VRAM de mayor ancho de banda. Windows distingue memoria de vídeo dedicada, memoria del sistema dedicada y memoria compartida por su forma de contabilización; esa clasificación no establece una jerarquía de velocidad. [Contabilidad de memoria en Windows](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/calculating-graphics-memory).

Las GPU UMA comparten memoria física con el host y pueden evitar copias de transferencia. Por tanto, no se descartan las integradas modernas ni los móviles por usar RAM compartida. [Guía de memoria Vulkan](https://docs.vulkan.org/guide/latest/memory_allocation.html). La UHD 630 fue más lenta para Gemma y no admitió Qwen dentro del plazo del ensayo; la comparación cambia simultáneamente GPU, arquitectura, ancho de banda y controlador, y no identifica una única causa.

El número de capas tampoco estima memoria de forma proporcional: Gemma a 36/36 llegó a 1831 MiB, mientras el GGUF ocupa 2,620 GB y el runtime mantiene buffers de CPU. La app debe registrar colocación y asignaciones reales, además de capas.

## Energía y elección en batería

| Lote de 15 casos en batería | Cambio aproximado de capacidad, CPU (Wh) | GPU (Wh) |
|---|---:|---:|
| Qwen | 18,873 | 6,711 |
| Gemma | 7,842 | 3,003 |

Se reconstruyeron esos valores a partir de las muestras WMI dentro de cada bloque. Incluyen el portátil entero y sus periodos de carga/calentamiento; las transiciones quedan parcialmente fuera. La caída entre las muestras interiores de toda la corrida fue 37,226 Wh. No es potencia instantánea de la GPU, energía exclusiva de inferencia ni estimación controlada de autonomía.

Los datos son compatibles con terminar antes y gastar menos energía total aun usando una GPU con mayor potencia instantánea. No se debe forzar CPU solo porque el equipo esté en batería. La sesión tuvo orden fijo, carga externa y temperatura variables; no hubo repetición aleatoria ni aislamiento de pantalla/procesos. El contador de potencia instantánea devolvió un centinela del controlador y no permite atribuir vatios a cada componente. Tampoco se puede prometer que el comportamiento se repita en todo equipo.

## Política para la aplicación final

Esta sección registra el diseño recomendado y la preferencia del usuario; **no afirma que el reparto adaptativo ya esté implementado en la aplicación**. El prototipo de escritorio/móvil conserva ABI 2 con CPU o descarga Vulkan completa. El portátil validó el selector de capas en una copia aislada de nuestro puente; no modificó upstream llama.cpp. La calibración CPU/Vulkan ya existente en el código compartido requiere ampliarse para registrar adaptador y colocaciones parciales.

1. **Proponer un modelo y comprobarlo localmente.** Priorizar Qwen 4B si una ruta Vulkan completa o parcial demuestra tiempos aceptables y memoria suficiente. Usar 4 GiB nominales solo como indicio previo a descargar; no como veto bajo ese número. Si Qwen queda lento, proponer Gemma. Con recursos más limitados, MiniCPM y finalmente LFM1.2, informando sus limitaciones conocidas. Mantener elección manual y no descargar otro modelo sin una acción del usuario.
2. **Separar elección de modelo y de backend.** Comparar CPU y GPU para el mismo GGUF. Tener Vulkan o poder cargar todas las capas no basta. Las integradas pasan por la misma comprobación; no habrá lista basada en nombres de teléfonos o GPU. Para el valor por defecto móvil, conservar Gemma como primera opción si cabe y responde adecuadamente, según la preferencia comunicada; Qwen permanece elegible si el dispositivo y las preferencias de calidad/espera lo justifican.
3. **Estimar antes de asignar.** Consultar RAM disponible y presupuesto actual del adaptador real. Contar pesos, contexto, caché/estado y buffers de cómputo con margen, usando las capacidades del runtime. Si no cabe la colocación completa, estimar directamente una parcial en lugar de provocar un fallo. No usar solo el tamaño GGUF, la RAM nominal, la etiqueta «dedicada» o una proporción de capas.
4. **Acotar la búsqueda.** Si una carga falla pese a la estimación, registrar etapa y error. Probar una colocación menor en un worker nuevo, con un número pequeño y límite temporal de candidatos, y pasar a CPU si fallan. Una capa menos es un candidato respaldado para este caso, no una regla de recuperación universal. Ante pérdida de dispositivo, no reutilizar el dispositivo lógico. Mantener el modelo descargado aunque una ruta GPU falle.
5. **Calibrar al preparar el modelo por primera vez.** Usar una tarea sintética representativa con los prompts, contexto y JSON de producción, calentamiento separado, progreso y cancelación. Medir prefill, decode, respuesta completa, tokens y memoria. Una única solicitud orienta, pero puede confundir compilación de shaders/caché con velocidad estable. Confirmar la selección con varias muestras y un margen prospectivo; el prototipo ya utiliza tres por backend y exige una mejora del 15 %. No usar respuestas de los 200 casos ni seleccionar por corrección lingüística durante esta calibración técnica.
6. **Guardar un perfil trazable.** Vincular el resultado al SHA del modelo, adaptador/driver, runtime/puente, contexto, prompt/gramática, hilos y colocación. Registrar alimentación y condiciones de la sesión. Revisar el presupuesto libre al cargar; recalibrar tras cambios relevantes o fallos, sin convertir la escasez transitoria en incompatibilidad permanente. Un perfil con batería puede complementar el de corriente si se ha medido; no inventar ahorro energético sin telemetría válida.
7. **Explicar la recomendación en la interfaz.** Mostrar el modelo y backend efectivos, por ejemplo «Vulkan, 32/33 capas en GPU», el motivo de CPU/fallback y la posibilidad de cambiar. Si Qwen es demasiado lento, ofrecer Gemma conservando Qwen. Las advertencias de JSON/coherencia siguen separadas de los fallos de carga o memoria.

El siguiente paso técnico es exponer y comprobar el número de capas y el adaptador mediante un contrato explícito en nuestro puente, integrar el presupuesto de memoria y extender la calibración existente. Esto puede realizarse usando las API disponibles sin modificar llama.cpp. La evidencia del portátil ya permite diseñar ese trabajo; no hace falta repetir las 200 preguntas ni ajustar prompts con este lote.

## Límites de reproducción

El primer fallo de Qwen no volcó picos de memoria; el segundo intento técnico sí quedó registrado. Los ejecutables de las sondas C++ no estaban en la copia entregada, aunque se conservaron sus hashes, fuentes y resultados; no se fabricaron ni reemplazaron. La DLL experimental sí estaba y se importó con sus seis dependencias verificadas. Los runners y manifiestos originales se preservan con sus rutas/perfiles; su existencia no autoriza volver a ejecutar automáticamente los experimentos.

Los RAW, registros técnicos y binarios permanecen locales e inventariados. Los informes, código y manifiestos pequeños se guardan en Git; no se añaden modelos o DLL. La conservación de los informes originales permite ver cómo los ensayos posteriores resolvieron pendientes de los anteriores. Este documento aporta la conclusión conjunta, sin convertir las conclusiones provisionales iniciales en el estado vigente.

# Prueba breve de recursos en portátil y criterio de selección

Fecha: 17 de noviembre de 2026. Preparación y aclaración de decisiones; no contiene mediciones nuevas. El portátil con Quadro P1000 aún no se ha inspeccionado ni conectado desde esta sesión.

## Por qué se preseleccionó MiniCPM y qué queda pendiente con Qwen 2B

Qwen3.5 2B Q4_K_M sí participó en las corridas comunes de 40 y 120 casos. La preselección para la revisión humana de tres configuraciones conservó Qwen 4B, Gemma E2B y MiniCPM 2B. No fue una demostración de que Qwen 2B sea universalmente inferior; el informe de preselección no explicó suficientemente esa comparación concreta.

Fuentes preservadas: `analysis_v2/results_40_current_16/configuration_summary.csv`, `analysis_v2/results_120/configuration_summary.csv` y `documentation/evaluation_v2_results_and_candidates.md`.

| Medida histórica | Qwen3.5 2B Q4_K_M | MiniCPM5 2B Q4_K_M |
|---|---:|---:|
| F0.5 textual primario, 40 casos | 0,5763 | 0,8393 |
| Textos incorrectos observables, de 30 | 28 | 30 |
| F0.5 textual primario, 120 casos | 0,6416 | 0,7682 |
| Textos incorrectos observables, de 90 | 89 | 88 |
| Precisión de ediciones, 120 | 0,6307 | 0,7887 |
| Recall de ediciones, 120 | 0,6894 | 0,6957 |
| Falsas alarmas en controles, de 30 | 5 | 3 |
| Controles cuyo texto se modifica, de 30 | 1 | 2 |
| Flag correcto en textos incorrectos, de 90 | 83 | 72 |
| Declaraciones coherentes sin ediciones vacías, de 120 | 62 | 91 |
| Esquema válido, de 120 | 114 | 116 |
| Mediana API histórica de 120, segundos | 1,183 | 0,842 |
| GGUF histórico, GB decimales | 1,274 | 1,561 |

F0.5 es una medida de ediciones que prioriza precisión; no es porcentaje de respuestas completamente correctas. Aquí es condicional a disponer de texto corregido observable. Los tiempos son descriptivos de la corrida compartida histórica en GPU del escritorio; no miden el portátil ni el teléfono.

MiniCPM presentó menos correcciones falsas, mejor coherencia y menor latencia en esa corrida. Qwen 2B presentó ventajas propias en tamaño de archivo, detección de textos incorrectos y preservación literal de controles. Estas diferencias justificaban una preselección provisional de MiniCPM, no eliminar Qwen 2B de futuras opciones.

Las corridas históricas usaban generación libre y el perfil de entonces. La aplicación actual usa prompts revisados, gramática JSON y otro runtime. Los excelentes resultados nuevos de Qwen 4B no prueban el comportamiento de Qwen 2B. Queda propuesta una comprobación breve de Qwen 2B frente a MiniCPM con el perfil actual, separada de la prueba de recursos de este documento. Usar datos de desarrollo, conservar RAW y no ajustar prompts con el test final de 200. No se ha ejecutado esa comprobación.

## Preferencia de producto comunicada por el usuario

Para la futura aplicación móvil, intentar Gemma E2B si el presupuesto de memoria y una carga técnica satisfactoria lo permiten; usar MiniCPM con memoria más limitada y LFM2.5 1.2B como alternativa extrema. Permitir siempre elección manual. LFM1.2 conserva limitaciones de fiabilidad; poder cargarlo no garantiza una evaluación correcta.

La preferencia se apoya en las observaciones comunicadas del POCO F3 y en los resultados disponibles. No equivale a una comparación móvil controlada de todos los modelos ni fija todavía umbrales de RAM. No se ha cambiado el código de recomendación en esta entrega.

## Instrucciones para Codex en el portátil

Objetivo: medir tiempo y memoria de Gemma E2B y Qwen3.5 4B en el portátil, especialmente CPU, con 15 mismos textos por configuración. No recalcular precisión con esa muestra ni repetir las 200 preguntas. Ejecutar localmente en Windows para usar el hardware real del portátil.

1. Leer este documento, `documentation/finalists_200_protocol_20261117.md`, `documentation/finalists_200_execution_20261117.md` y `manifests/finalists_200_20261117.json`. Preservar los resultados y artefactos congelados. La solicitud actual plantea esta prueba; documentar el protocolo reducido antes de ejecutarla.
2. Inventariar CPU, núcleos físicos/lógicos, RAM total/disponible, Windows, alimentación/modo energético, adaptadores, controladores y VRAM real. Hay una Quadro P1000 según el usuario; no asumir memoria, soporte útil de Vulkan ni que el adaptador elegido sea el correcto si también existe una GPU integrada.
3. Copiar el proyecto y los activos necesarios por un medio local. Este repositorio no tiene remoto; no publicar ni configurar uno para transferirlo. Las rutas absolutas y la junction `models` del escritorio no son portables. Los GGUF y DLL ignorados por Git deben transferirse o adquirirse por separado y verificarse. El ZIP de evidencia de las 200 preguntas no contiene pesos ni DLL nativas.
4. Seleccionar y guardar antes de generar 15 entradas comunes del benchmark de desarrollo de 120: 7 A1 y 8 A2, con 11 incorrectas y 4 controles, incluyendo distintas longitudes. Usar una regla determinista documentada sin escoger por respuestas o resultados anteriores. Guardar solo ID, nivel, consigna y texto para el worker; no transmitir gold. Registrar SHA del origen y del subconjunto. Mantener el mismo orden en los dos modelos y backends.
5. Crear un runner y manifiesto separados y portables, reutilizando el contrato y la telemetría existentes. **No ejecutar ni modificar directamente `run_finalists_200.py`**: está vinculado a 200 casos, rutas del escritorio y hashes congelados. Guardar derivados en un directorio nuevo, por ejemplo `results_laptop_resources_v1/`, sin sobrescribir resultados anteriores.
6. Medir primero 15 casos en CPU con cada modelo: 30 respuestas puntuables para recursos. Una sola configuración cargada; cero capas GPU en CPU y backend efectivo comprobado. Registrar carga y un calentamiento sintético aparte por carga. Mantener contexto 2048, máximo 512 tokens, semilla 42, thinking desactivado, prompts, sampling y gramática del manifiesto de escritorio. No igualar artificialmente el sampling entre familias ni cambiarlo según las respuestas. Sin reintentos por calidad o JSON. Fijar antes un plazo técnico razonable para CPU más lenta, por ejemplo 600 segundos, y registrarlo como diferencia de protocolo.
7. Si Vulkan supera readiness y cabe de forma segura, medir los mismos 15 por modelo en Vulkan: hasta otras 30 respuestas, con los calentamientos separados. Registrar dispositivo real y capas descargadas a GPU. Si solo cabe descarga parcial, tratarla como configuración distinta y declarar las capas antes del bloque; no llamarla GPU completa ni mezclarla con CPU. No introducir CUDA o cambiar runtime para salvar una comparación fallida. Guardar los fallos y continuar con la evidencia CPU que sí pueda obtenerse.
8. Configurar `PYTHONIOENCODING=utf-8` en los procesos Python y comunicación UTF-8 explícita. Conservar inicios de intento y RAW con escritura duradera antes de interpretar. La primera corrida de escritorio requirió reiniciarse por un problema técnico de codificación; no reproducirlo.
9. Mantener el portátil conectado a corriente y sin suspensión durante la medición. Registrar modo energético, temperaturas y carga externa cuando se puedan medir; no cerrar aplicaciones ajenas sin autorización. Evitar dos modelos o pruebas simultáneos. El orden por bloques y la muestra pequeña limitan las conclusiones.
10. Publicar filas individuales, RAW, fallos y un resumen Markdown/CSV: mediana, media y rango de latencia total; prefill/decode, tokens generados y tokens/s; tiempo de carga; pico muestreado de RSS y memoria privada del worker y descendientes; RAM disponible mínima; VRAM del adaptador con línea base y pico si la telemetría lo permite. La VRAM global incluye otros procesos. No sumar RSS y VRAM como si fuesen memoria exclusiva del modelo. Mostrar tiempo de salida completa y velocidad por token, pues las longitudes de respuesta pueden diferir. Con 15 casos, no presentar percentiles extremos como estimaciones robustas ni extrapolar a todos los portátiles.

El informe debe separar resultado observado, fallos técnicos, compatibilidad de GPU y recomendación. No modificar llama.cpp ni parámetros para mejorar calidad durante esta prueba. La latencia de una conexión remota no debe incluirse en el tiempo nativo de inferencia.

## Activos exactos de la comparación actual

Fuente canónica: `manifests/finalists_200_20261117.json`. Remapear rutas en un manifiesto nuevo conservando los hashes de los bytes transferidos.

| Activo | Tamaño en bytes | SHA-256 |
|---|---:|---|
| `gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf` | 2620370976 | `e531007218dfab990486a5de7676a6932d6ea8dea233d1f698d7c21cf8a16889` |
| `Qwen3.5-4B-Q4_K_M.gguf`, descargable Unsloth | 2740937888 | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |

No sustituir el segundo por el Qwen 4B convertido localmente usado en la fase de 120: son activos distintos. Runtime: llama.cpp b12359, commit `b1b770d90d94cad9e9ea5b993bdbc383a522fb28`, puente ABI 2. Transferir las siete DLL de `cross_demo/native/artifacts/b12359/win-x64/` y contrastarlas con `source_bindings` del manifiesto. La CPU del portátil debe superar una carga técnica; la compatibilidad del binario no se deduce solo de tener Windows x64.

## Forma recomendada de trabajar

Para esta prueba puntual, abrir una sesión de Codex **en el portátil**, sobre la copia del proyecto, y darle este archivo. Así comandos y mediciones usan directamente ese equipo. Este documento prepara el traspaso; todavía no es un paquete ejecutable autónomo ni se ha transferido nada.

La documentación oficial también describe conexión a otro equipo mediante `Settings > Connections > Control other devices`, cuando esté disponible, y proyectos remotos por SSH. Requieren configurar el host; tener Codex instalado en dos equipos no da acceso automático de esta sesión al otro. Referencia consultada: [Remote connections](https://learn.chatgpt.com/docs/remote-connections). No se ha habilitado acceso remoto ni creado una sesión remota en esta entrega.

Mensaje sugerido para pegar en Codex del portátil:

> Lee `SLM_A1A2/documentation/laptop_performance_handoff_20261117.md` y prepara la prueba breve indicada sobre este portátil. Comprueba primero hardware y activos. Conserva resultados anteriores y artefactos congelados, usa 15 mismos casos de desarrollo por modelo, mide CPU y Vulkan cuando sea viable y documenta resultados y límites. No repitas el benchmark de 200 ni modifiques llama.cpp. Si falta algún activo, identifica el archivo y hash concretos antes de sustituirlo.

# Recursos de Gemma 4 E2B y Qwen3.5 4B en el HP ZBook

18 de noviembre de 2026 (UTC−5). Prueba local de latencia, memoria y compatibilidad con un worker activo por bloque. Los 15 textos de desarrollo se fijaron antes de la primera inferencia y se enviaron en el mismo orden a cada configuración admitida.

## Equipo y activos

HP ZBook Studio x360 G5 con Intel Core i9‑8950HK (6 núcleos, 12 hilos), 35,81 GiB de RAM total y 12,44 GiB disponibles en el inventario. Windows 11 Pro, compilación 26300. Conectado a corriente y con el plan Alto rendimiento. El proceso solicitó inhibir la suspensión durante la medición. [Inventario y salida de Vulkan](host.json)

Intel UHD Graphics 630 con controlador 31.0.101.2141 y Vulkan 1.3.215. NVIDIA Quadro P1000 con 4096 MiB de VRAM según `nvidia-smi`, controlador 582.53 en modo WDDM, Vulkan 1.4.312 y PCI `01:00.0`. La Quadro aparece como GPU1 al enumerar Vulkan. La identidad de la carga se verifica por el PCI del log nativo. [Inventario y salida de Vulkan](host.json)

Los dos GGUF faltaban en la copia local. Se registraron tamaño y SHA-256 esperados antes de descargar los bytes de las revisiones fijadas. Los tamaños y hashes locales coincidieron con el manifiesto, al igual que las siete DLL de llama.cpp b12359, commit `b1b770d90d94cad9e9ea5b993bdbc383a522fb28`, puente ABI 2. [Adquisición](asset_acquisition.json) · [Verificación local](verified_assets.json)

| Archivo exacto | Bytes | SHA-256 |
|---|---:|---|
| [gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf](https://huggingface.co/unsloth/gemma-4-E2B-it-qat-GGUF/blob/66a399f68ddd113b06dff02fca9523e55465d11d/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf) | 2 620 370 976 | `e531007218dfab990486a5de7676a6932d6ea8dea233d1f698d7c21cf8a16889` |
| [Qwen3.5-4B-Q4_K_M.gguf](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/blob/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf) | 2 740 937 888 | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |

## Diseño y trazabilidad

Muestra de 7 A1 y 8 A2, con 11 incorrectos y 4 controles de 24 a 57 palabras. Se eligieron posiciones equiespaciadas por longitud dentro de cada estrato y se fijó el orden mediante SHA-256 del identificador con la semilla documentada. La fuente de 120 casos tiene SHA-256 `07308427c02adcc056a8964d3e4da41615db4b7fc0101870e277097de46d59f9`. El subconjunto, que contiene ID, nivel, consigna y texto, tiene SHA-256 `bcb795c97a56287400c65fe9a54f41e930f2eb445e93e14ab56e2175dffe9f77`. [Protocolo previo](../documentation/laptop_resources_protocol_v1.md) · [Manifiesto](manifest.json) · [Subconjunto](cases.json)

Se mantuvieron contexto 2048, salida máxima 512 tokens, semilla 42, plantilla nativa, thinking desactivado, gramática JSON y prompt y sampling específicos de cada familia. Cada carga satisfactoria se siguió de un calentamiento sintético fuera de la muestra. El plazo técnico fue de 600 s por carga o generación, frente a los 120 s del protocolo de escritorio. El worker usó UTF-8 explícito y una sonda con `café` antes de cada carga. El registro de intentos y el RAW se sincronizaron a disco. [Runner](../run_laptop_resources.py)

## Resultado observado

La corrida principal transcurrió de 17:39 a 18:16 (hora de Ecuador continental). Hubo **45 respuestas** con estado nativo satisfactorio y fin `stop`. La auditoría confirmó los mismos 15 IDs en el mismo orden en cada bloque completado, un intento por caso y correspondencia por SHA-256 entre RAW y telemetría. [Resumen CSV](summary.csv) · [Filas individuales CSV](cases.csv) · [Registro de cierre](completion.json)

| Configuración | Casos | Total mediana / media (s) | Rango total (s) | Prefill / decode medianos (s) | Tokens generados medianos | Decode / salida completa (tokens/s, medianas) |
|---|---:|---:|---:|---:|---:|---:|
| Gemma / CPU | 15/15 | 37,20 / 40,41 | 27,56–58,30 | 9,32 / 27,64 | 219 | 7,94 / 5,91 |
| Qwen / CPU | 15/15 | 84,13 / 84,81 | 56,01–131,86 | 36,70 / 47,16 | 190 | 4,33 / 2,18 |
| Gemma / Vulkan | 15/15 | 8,88 / 9,34 | 5,77–15,00 | 1,20 / 7,49 | 207 | 27,70 / 22,49 |
| Qwen / Vulkan | 0/15 | — | — | — | — | — |

Con Gemma, el cociente mediano por caso entre latencia CPU y Vulkan fue 4,73. La mejora coincide con un prefill más corto y con mayor velocidad de decode en Vulkan. En CPU, Gemma tuvo menor latencia mediana y mayor velocidad de decode que Qwen con estos perfiles.

| Configuración | Carga / calentamiento (s) | RSS pico (GiB) | Privada pico (GiB) | RAM disponible mínima (GiB) | VRAM base → pico (MiB) |
|---|---:|---:|---:|---:|---:|
| Gemma / CPU | 3,34 / 32,00 | 2,68 | 2,05 | 9,45 | 0 → 0 |
| Qwen / CPU | 4,94 / 70,65 | 4,15 | 2,32 | 8,29 | 0 → 0 |
| Gemma / Vulkan | 3,25 / 23,57 | 1,81 | 2,44 | 11,13 | 0 → 1831 |
| Qwen / Vulkan, segunda carga fallida | — | 1,15 | 3,21 | 11,84 | 0 → 2606 |

El uso global de CPU previo a los cuatro bloques fue 24,6 %, 16,0 %, 19,0 % y 19,7 %, en ese orden. Durante las configuraciones completas se registraron 1446 muestras de alimentación, todas con corriente conectada. La Quadro alcanzó 76 °C en Gemma/Vulkan. La zona ACPI `CPUZ` registró 64,1–85,1 °C en la parte observada de Gemma/CPU, 65,1–89,1 °C en Qwen/CPU y 73,1–89,1 °C en Gemma/Vulkan. [Registro térmico ACPI](cpu_thermal_acpi.jsonl) · [Telemetría por caso](telemetry/)

## Compatibilidad y fallos

- **CPU.** En ambos modelos, el puente confirmó backend CPU y cero capas en GPU. Los dos calentamientos y los 30 casos completaron.
- **Gemma/Vulkan.** El log confirmó la Quadro P1000 por PCI `01:00.0`, 3617 MiB libres al iniciar la carga y 36/36 capas descargadas. El calentamiento llegó a 1821 MiB de VRAM global y el pico del bloque fue 1831 de 4096 MiB. La colocación de capas conserva buffers del modelo mapeados en CPU, que el log cuantifica por separado. [Log nativo](logs/13-gemma4-e2b-ud-q4-k-xl--vulkan.log) · [Readiness](readiness/13-gemma4-e2b-ud-q4-k-xl--vulkan.json)
- **Qwen/Vulkan.** El log identificó la misma Quadro y 3617 MiB libres. Tras anunciar la colocación de 33/33 capas, falló en `vk::Queue::submit: ErrorDeviceLost` durante la carga. Con la Quadro nuevamente operativa y ociosa, se hizo una única comprobación técnica adicional en una carpeta aparte. Usó los mismos binarios, pesos, perfil, subconjunto y umbrales, y reprodujo el mismo error antes del calentamiento. En el segundo intento se observaron 2606 MiB de VRAM global al pico muestreado, con 0 MiB de base y 58 °C de temperatura inicial. El código del error y la telemetría dejan la causa sin determinar. El ABI de la aplicación expone CPU y descarga completa, de modo que la descarga parcial quedó sin medir. [Log inicial](logs/portable-unsloth-qwen35-4b-q4-k-m--vulkan.log) · [Log de la comprobación](qwen_vulkan_retry/logs/portable-unsloth-qwen35-4b-q4-k-m--vulkan.log) · [CSV de la carga fallida](qwen_vulkan_retry/summary.csv)
- El primer fallo de carga dejó sin volcar los picos de ese intento y produjo un error de cierre de tubería (`OSError 22`). Los tres bloques completos y el fallo original quedaron guardados. El runner archivado conserva el SHA del manifiesto principal. Para la segunda comprobación se corrigió el cierre y se guardó la telemetría de carga fallida. [Fallo inicial](failures.jsonl) · [Runner archivado](runner_used.py) · [Manifiesto de la comprobación](qwen_vulkan_retry/manifest.json)

## Recomendación para este portátil

Para priorizar tiempo de respuesta en este equipo, usar Gemma con Vulkan y mantener Gemma en CPU como alternativa. Qwen tiene una ruta CPU verificada, con una mediana de 84,13 s. La decisión de calidad y cualquier recomendación para móviles requieren evidencia de esas evaluaciones.

## Límites

- Los resultados son descriptivos de esta sesión, este portátil, estos perfiles y estos 15 textos. El orden fijo de los bloques puede mezclar el efecto del backend con la temperatura y la carga concurrente. Las longitudes generadas varían, por lo que conviene leer juntos el tiempo hasta la respuesta completa y los tokens por segundo. La muestra se utilizó exclusivamente para recursos.
- La carga sigue a la verificación de los pesos por lectura completa y puede beneficiarse de la caché de archivos de Windows. El tiempo nativo corresponde al puente local. El CSV individual incluye también el tiempo de la llamada al worker y el tiempo de petición del coordinador.
- RSS y memoria privada son picos muestreados del árbol del worker. RSS incluye páginas mapeadas o compartidas y la memoria privada comprometida puede incluir páginas fuera del conjunto residente. La RAM libre mínima abarca todo el sistema. La VRAM en modo WDDM incluye la actividad de otros procesos y el pico muestreado puede omitir transitorios.
- La temperatura de CPU corresponde a la zona ACPI `CPUZ`, observada desde parte del bloque Gemma/CPU, a intervalos de unos 20 s. La carga del sistema durante cada bloque incluye la inferencia. La medición anterior al bloque sirve como referencia de actividad concurrente.

## Evidencia

- [RAW](raw/) · [Inicios de intento](attempts/) · [Telemetría](telemetry/) · [Cargas y calentamientos](readiness/) · [Logs nativos](logs/)
- [Constancia del segundo intento técnico](qwen_vulkan_retry/retry_reason.json) · [Fallo](qwen_vulkan_retry/failures.jsonl) · [Telemetría de carga](qwen_vulkan_retry/readiness/portable-unsloth-qwen35-4b-q4-k-m--vulkan.json)

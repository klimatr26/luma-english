# Velocidad de generación de Qwen híbrido y Vulkan integrado

18 de noviembre de 2026, hora de Ecuador continental. Ensayo local en el HP ZBook Studio x360 G5, con Intel Core i9‑8950HK y Windows 11 Pro. Cada bloque usa los mismos 15 textos de desarrollo, en el mismo orden, con los perfiles de escritura congelados. La muestra tiene 7 A1 y 8 A2, con 11 textos incorrectos y 4 controles. [Protocolo previo](protocol.md) · [Manifiesto](manifest.json) · [Textos enviados](cases.json)

## Equipo y método

- La Quadro P1000 dispone de 4096 MiB de VRAM según NVIDIA, controlador 582.53 y PCI `0000:01:00.0`. La UHD Graphics 630 usa RAM compartida, controlador 31.0.101.2141 y Vulkan 1.3.215. GGML inicializó la Intel y publicó una capacidad de memoria de 17,91 GiB para el dispositivo UMA. Esa cifra corresponde a memoria del sistema accesible desde el adaptador. [Inventario](host.json) · [Sonda Intel](intel_preflight.json)
- El runner selecciona exclusivamente el adaptador de cada bloque y confirma su nombre efectivo y el conteo de capas en el log. Se verificaron los dos GGUF y seis DLL b12359. Se compiló una copia aislada del puente de escritura con un selector de capas mediante el entorno. El perfil conserva plantillas, prompt, gramática, sampling, semilla 42, contexto 2048 y 512 tokens máximos de salida. Los resultados y artefactos anteriores se preservaron. [Construcción y hashes](bridge_build.json) · [Runner](../run_laptop_hybrid_gpu.py)
- Se registra carga y un calentamiento sintético por bloque, además del tiempo nativo total, prefill y decode de cada solicitud real de desarrollo. Los tokens/s de decode usan tokens procesados durante la fase de decode. Los tokens/s de salida completa dividen los tokens generados por el tiempo nativo total. [Guía de detección híbrida](../documentation/vulkan_hybrid_detection_20261118.md)

## Resultados

Hubo 30 respuestas con estado nativo satisfactorio y fin `stop`. Los dos bloques completos usaron los 15 IDs previstos con un intento por caso. Los registros de telemetría corresponden al RAW mediante SHA-256. [Resumen CSV](summary.csv) · [Filas individuales](cases.csv) · [Registro de cierre](completion.json)

| Modelo y GPU | Capas | Casos | Total mediana / media (s) | Rango (s) | Prefill / decode medianos (s) | Tokens generados medianos | Decode / salida completa (tokens/s, medianas) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen · Quadro P1000 | 32/33 | 15/15 | 23,22 / 23,99 | 13,75–38,74 | 8,16 / 14,63 | 192 | 13,08 / 8,27 |
| Qwen · Intel UHD 630 | 33/33 | 0/15 | — | — | — | — | — |
| Gemma · Intel UHD 630 | 36/36 | 15/15 | 45,48 / 45,05 | 28,63–63,68 | 9,75 / 35,49 | 227 | 6,69 / 5,06 |

**Qwen híbrido en la Quadro.** Cargó en 4,32 s y calentó en 28,83 s. Frente a los mismos casos en la corrida CPU previa, cuya mediana fue 84,13 s y 4,33 tokens/s de decode, el cociente mediano por caso fue **3,59×**. Vulkan híbrido fue más rápido en los 15 casos. El recuento de 32/33 corresponde al dispositivo PCI verificado. [Log nativo](logs/qwen--quadro-p1000--32.log) · [Calentamiento](readiness/qwen--quadro-p1000--32.json)

**Qwen en la Intel.** Cargó en 6,07 s con 33/33 capas y creó el contexto. El calentamiento excedió el plazo de 120 s sin devolver una respuesta. El worker se cerró y el bloque quedó sin casos enviados. La ruta completa en Intel quedó por debajo del criterio de admisión práctico de este ensayo. La ejecución no produjo medidas nativas de prefill o decode para ese calentamiento. La variante condicional de 16 capas se había reservado para un fallo de asignación durante la carga. [Log nativo](logs/qwen--intel-uhd630--all.log) · [Fallo de calentamiento](readiness/qwen--intel-uhd630--all.json)

**Gemma en la Intel.** Cargó en 3,11 s y calentó en 70,71 s. La Intel fue más rápida que la CPU en 5/15 casos pareados. La diferencia mediana por caso fue de +3,33 s (Intel menos CPU), y las medianas de los bloques fueron 45,48 s en Intel, 37,20 s en CPU y 8,88 s en la Quadro. La tasa mediana de decode en CPU fue 7,94 tokens/s. En este portátil la Intel sirve de ruta técnica para Gemma y la CPU dio menor latencia típica. [Log nativo](logs/gemma--intel-uhd630--all.log) · [Calentamiento](readiness/gemma--intel-uhd630--all.json) · [Mediciones previas](../results_laptop_resources_v1/report.md)

## Memoria y límites

| Bloque | RSS pico (GiB) | Privada pico (GiB) | RAM disponible mínima (GiB) | Memoria global del adaptador al pico |
|---|---:|---:|---:|---:|
| Qwen · Quadro | 3,33 | 4,13 | 10,88 | 3165 MiB de VRAM, con base de 0 MiB |
| Qwen · Intel | 3,83 (carga) | 4,11 (carga) | 10,43 (carga) | 4,37 GiB compartidos, incluida la espera del calentamiento |
| Gemma · Intel | 3,67 | 3,75 | 12,66 | 2,70 GiB compartidos |

La Quadro alcanzó 73 °C. Los contadores WDDM de Intel se tomaron cada 15 s aproximadamente, con el LUID `luid_0x00000000_0x00011714_phys_0` verificado en Vulkan. Son globales al adaptador e incluyen procesos del sistema. El uso compartido era de 0,55 GiB en la muestra anterior a Qwen/Intel. El contador dedicado de Intel permaneció en cero en la muestra. RSS, memoria comprometida y memoria compartida describen magnitudes distintas. [Muestras WDDM](intel_wddm.jsonl) · [Identidad del adaptador](adapter_luids.txt)

La primera sonda Intel intentó abrir el plugin por una ruta directa y falló en esa apertura. Al usar el mismo cargador de directorio que usa la app, la inicialización Intel tuvo éxito. El ensayo de generación usó este segundo mecanismo. [Primer intento de apertura](intel_preflight_direct_path.log) · [Inicialización válida](intel_preflight.log)

Las comparaciones con CPU y Gemma/Quadro corresponden a sesiones distintas sobre la misma máquina. La temperatura, la carga concurrente, la caché de archivos y las longitudes de respuesta pueden cambiar entre bloques. La muestra sirve para estimar latencia y recursos locales. El resultado híbrido respalda ofrecer Qwen en la Quadro con este perfil cuando se prioriza el modelo. Con la Intel como única GPU, las configuraciones probadas favorecen Gemma en CPU por latencia. [RAW](raw/) · [Intentos](attempts/) · [Telemetría](telemetry/) · [Fallos](failures.jsonl)

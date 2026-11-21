# Simulación de 2 GiB de VRAM con capas en CPU y Vulkan

18 de noviembre de 2026, hora de Ecuador continental. Ensayo local en el HP ZBook Studio x360 G5 con Core i9‑8950HK y Quadro P1000. Windows detectó corriente conectada y plan Alto rendimiento para este ensayo. Se reutilizaron los mismos 15 textos de desarrollo y su orden. [Protocolo](protocol.md) · [Manifiesto](manifest.json) · [Inventario](host.json)

La tarjeta física conserva sus 4096 MiB de VRAM. Se simula un presupuesto de 2048 MiB mediante la colocación de capas, con un requisito de 1920 MiB o menos en carga y calentamiento para dejar margen. Se valida el uso global muestreado durante la generación. Una tarjeta física de 2 GiB puede ofrecer un presupuesto efectivo distinto y otras prestaciones de cómputo, memoria y controlador.

Se eligieron 14 de 33 capas para Qwen, a partir del pico previo de 2053 MiB con 16 capas en la sonda corta. Gemma usa 18 de 36. Los bloques restantes se colocan en CPU. Se verificaron los pesos y las DLL b12359, y se reutilizó la copia aislada del puente con selección de capas. Se conservan contexto 2048, máximo 512 tokens, prompts, sampling, semilla 42 y gramática de escritura. [Subconjunto](cases.json) · [Runner](../run_laptop_vram2g.py) · [Sonda previa](../results_laptop_qwen_vulkan_diagnostic_v1/report.md)

## Resultados

Se completaron 30 de 30 solicitudes de desarrollo entre las 20:45 y las 21:03. Todas tuvieron estado nativo satisfactorio y fin `stop`. Se verificaron los mismos IDs en el mismo orden, un intento por caso y el vínculo SHA-256 de cada respuesta RAW con su telemetría. La Quadro se confirmó por PCI `0000:01:00.0` en ambos bloques. [Resumen CSV](summary.csv) · [Filas individuales CSV](cases.csv) · [Cierre](completion.json)

| Modelo | Capas en GPU | Casos | Latencia mediana / media (s) | Rango (s) | Prefill / decode medianos (s) | Tokens generados medianos | Decode / salida completa (tokens/s, medianas) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen 3.5 4B | 14/33 | 15/15 | 46,12 / 43,27 | 21,48–65,83 | 9,15 / 36,55 | 207 | 5,65 / 4,43 |
| Gemma 4 E2B | 18/36 | 15/15 | 17,90 / 19,97 | 11,15–33,75 | 1,65 / 16,05 | 207 | 12,64 / 11,26 |

| Modelo | Carga / calentamiento (s) | VRAM global base → pico (MiB) | Margen hasta 2048 MiB | RSS / privada pico (GiB) | RAM disponible mínima (GiB) |
|---|---:|---:|---:|---:|---:|
| Qwen · 14 capas | 3,18 / 38,76 | 0 → 1920 | 128 MiB | 3,32 / 2,93 | 13,25 |
| Gemma · 18 capas | 2,89 / 19,53 | 0 → 1347 | 701 MiB | 1,79 / 1,96 | 15,01 |

Qwen llegó a 1909 MiB durante la carga y a 1920 MiB desde el calentamiento. Gemma pasó de 1329 MiB en carga a 1339 MiB en el calentamiento y 1347 MiB durante los casos. La Quadro alcanzó 70 °C con Qwen y 71 °C con Gemma. El consumo de VRAM es global al adaptador, con muestreo nominal de un segundo.

## Comparación sobre los mismos casos con corriente

| Modelo | CPU, mediana (s) | Vulkan parcial simulado, mediana (s) | Vulkan con más capas, mediana (s) | Aceleración pareada de CPU a parcial |
|---|---:|---:|---:|---:|
| Qwen 3.5 4B | 84,13 | 46,12 | 23,22 con 32/33 | 1,82× |
| Gemma 4 E2B | 37,20 | 17,90 | 8,88 con 36/36 | 2,06× |

La aceleración pareada es la mediana de `latencia CPU / latencia parcial` por ID. Ambos bloques parciales fueron más rápidos que CPU en los 15 casos. Comparada con la configuración que descarga más capas, la latencia parcial fue 1,81× en Qwen y 2,14× en Gemma, según los cocientes pareados. Son comparaciones descriptivas de sesiones distintas. La longitud de salida puede variar por backend. [CPU y Gemma 36/36](../results_laptop_resources_v1/report.md) · [Qwen 32/33](../results_laptop_hybrid_gpu_v1/report.md)

**Qwen a 14/33** es una configuración híbrida validada bajo el presupuesto observado. La mayor reducción frente a CPU estuvo en prefill, cuya mediana pasó de 36,70 a 9,15 s. El log registró 1350,06 MiB para el búfer de pesos en GPU y 505,00 MiB para el de cómputo, además de caché y estado recurrente.

**Gemma a 18/36** deja más margen. La referencia anterior de **36/36** ya alcanzaba un pico de **1831 MiB** en esta Quadro, porque parte de los pesos permanece mapeada en CPU incluso en esa colocación. Por eso, para Gemma el conteo de capas por sí solo da una estimación pobre del consumo. La colocación completa merece una comprobación real si el presupuesto efectivo del dispositivo lo permite. [Log de Gemma 36/36](../results_laptop_resources_v1/logs/13-gemma4-e2b-ud-q4-k-xl--vulkan.log)

## Evidencia

- [RAW](raw/) · [Intentos](attempts/) · [Telemetría](telemetry/) · [Cargas y calentamientos](readiness/)
- [Log Qwen 14/33](logs/qwen--quadro--14.log) · [Log Gemma 18/36](logs/gemma--quadro--18.log)

# Prueba final de Qwen y Gemma en batería

18 de noviembre de 2026, hora de Ecuador continental. Ensayo local en el HP ZBook Studio x360 G5, Intel Core i9‑8950HK de 6 núcleos y 12 hilos, 35,81 GiB de RAM, Windows 11 Pro y NVIDIA Quadro P1000 con 4096 MiB y controlador 582.53. Se reutilizaron los mismos 15 textos de desarrollo, en el mismo orden, que en las mediciones con corriente. [Protocolo](protocol.md) · [Manifiesto](manifest.json) · [Subconjunto](cases.json)

## Condiciones

- Windows detectó alimentación de batería, plan Alto rendimiento y ahorro desactivado al inicio. Bajo ese plan, Windows informa estado mínimo del procesador del 5 % en batería y 100 % con corriente, y estado máximo del 100 % en ambos. Durante la ejecución se solicitó inhibir la suspensión por inactividad. El umbral de cierre de la prueba quedó fijado en 12 %, frente a la hibernación crítica configurada al 5 %. [Inventario y plan](host.json)
- Se usaron los pesos y DLL exactos de las referencias con corriente, incluido el puente experimental de Qwen/Vulkan y el puente congelado en los otros tres bloques. Se mantuvieron prompts, sampling, contexto de 2048, gramática JSON, semilla 42 y máximo de 512 tokens. Cada bloque tiene un calentamiento sintético separado. La latencia de casos se mide localmente en el puente. [Runner](../run_laptop_battery.py)
- El orden fue Qwen/Vulkan, Gemma/Vulkan, Gemma/CPU y Qwen/CPU. Se comprobó alimentación antes y durante cada solicitud, y se registraron porcentajes, estado de ahorro y capacidad de batería reportada por Windows. Los valores de capacidad y VRAM representan al sistema o adaptador completo. [Estado de energía de Windows](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-system_power_status)

## Resultado

Se completaron **60 de 60 solicitudes**, con fin nativo `stop` en todas. La corrida duró **41 min 10 s**, de 19:54:38 a 20:35:48. La carga cayó del **96 % al 37 %**. Las 1770 muestras de los bloques registraron batería y ahorro desactivado. Se verificó un intento por caso, coincidencia de IDs y orden, y correspondencia entre las salidas RAW y su telemetría por SHA-256. [Cierre](completion.json) · [Límites de alimentación](power_bounds.json)

| Modelo y backend | Capas GPU | Casos | Total mediana / media (s) | Rango total (s) | Prefill / decode medianos (s) | Tokens generados medianos | Decode / salida completa (tokens/s, medianas) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen · Vulkan Quadro | 32/33 | 15/15 | 25,37 / 26,08 | 14,37–43,79 | 8,31 / 16,35 | 192 | 11,84 / 7,57 |
| Gemma · Vulkan Quadro | 36/36 | 15/15 | 9,63 / 9,73 | 6,16–16,47 | 1,24 / 8,03 | 207 | 25,65 / 21,31 |
| Gemma · CPU | 0 | 15/15 | 33,59 / 35,55 | 21,02–50,03 | 7,25 / 24,74 | 219 | 9,17 / 7,02 |
| Qwen · CPU | 0 | 15/15 | 74,87 / 79,18 | 56,06–119,79 | 34,44 / 43,13 | 190 | 4,51 / 2,40 |

En batería, el cociente mediano de latencia CPU/Vulkan por caso fue **3,03× para Qwen** y **3,29× para Gemma**. El log identificó la Quadro por PCI `0000:01:00.0` y confirmó la colocación de capas en ambos bloques. [Resumen CSV](summary.csv) · [Filas individuales CSV](cases.csv)

## Comparación con corriente

| Configuración | Mediana con corriente (s) | Mediana en batería (s) | Cambio de latencia pareado mediano |
|---|---:|---:|---:|
| Qwen · Vulkan 32/33 | 23,22 | 25,37 | +8,0 % |
| Gemma · Vulkan 36/36 | 8,88 | 9,63 | +7,4 % |
| Gemma · CPU | 37,20 | 33,59 | −17,4 % |
| Qwen · CPU | 84,13 | 74,87 | −7,0 % |

El cambio pareado es la mediana de `100 × (latencia en batería / latencia con corriente − 1)` entre los 15 IDs. Ambos bloques CPU tuvieron menos carga de sistema antes de empezar en batería que en su referencia con corriente. Fue 6,9 % frente a 24,6 % para Gemma, y 8,7 % frente a 16,0 % para Qwen. Los cambios describen dos sesiones con orden, carga concurrente y condiciones térmicas variables. [Referencia CPU y Gemma/Vulkan](../results_laptop_resources_v1/report.md) · [Referencia Qwen/Vulkan 32/33](../results_laptop_hybrid_gpu_v1/report.md)

## Batería, memoria y temperaturas

| Configuración | Batería inicio → fin | Cambio aproximado de capacidad (Wh) | Carga / calentamiento (s) | RSS / privada pico (GiB) | RAM disponible mínima (GiB) | VRAM global base → pico (MiB) |
|---|---:|---:|---:|---:|---:|---:|
| Qwen · Vulkan 32/33 | 96 → 84 % | 6,71 | 4,26 / 23,74 | 3,30 / 4,14 | 12,62 | 0 → 3165 |
| Gemma · Vulkan 36/36 | 84 → 80 % | 3,00 | 3,15 / 9,64 | 1,67 / 2,35 | 14,51 | 0 → 1831 |
| Gemma · CPU | 80 → 67 % | 7,84 | 3,06 / 43,04 | 2,69 / 2,05 | 13,29 | 0 → 0 |
| Qwen · CPU | 67 → 37 % | 18,87 | 4,27 / 69,03 | 4,15 / 2,33 | 11,92 | 0 → 1 |

Entre la primera y la última muestra WMI dentro de la corrida, la capacidad restante bajó de 60,96 a 23,74 Wh, una diferencia de **37,23 Wh**. La capacidad de carga completa que informó Windows fue de 63,79 Wh. El cambio por bloque usa sus muestras extremas interiores, excluye parte de los intervalos de transición y refleja el portátil completo, incluidos pantalla y procesos concurrentes. La tasa instantánea de descarga llegó con el valor centinela del controlador. La reducción de capacidad se calculó a partir de las lecturas de capacidad restante. [Muestras de batería](battery_wmi.jsonl)

La zona térmica ACPI de CPU registró 62–85 °C en toda la corrida. La Quadro llegó a 67 °C con Qwen/Vulkan y 68 °C con Gemma/Vulkan. RSS y memoria privada son picos muestreados del árbol del worker. La VRAM es global a la Quadro bajo WDDM y puede incluir inicialización del plugin y otros procesos. Los valores observados de VRAM en CPU son compatibles con cero capas descargadas.

**En este portátil, Qwen con 32/33 capas mantuvo una mediana de 25,37 s en batería.** Gemma con 36/36 capas ofreció la menor latencia de las cuatro configuraciones medidas. Cuando se usa CPU, Gemma obtuvo la menor latencia típica. La prueba mide recursos y velocidad en 15 casos comunes.

## Evidencia

- [Salida RAW](raw/) · [Inicios de intento](attempts/) · [Telemetría por caso](telemetry/) · [Cargas y calentamientos](readiness/)
- [Log Qwen/Vulkan](worker_hybrid/logs/qwen--quadro-p1000--32.log) · [Log Gemma/Vulkan](worker_original/logs/13-gemma4-e2b-ud-q4-k-xl--vulkan.log) · [Log Gemma/CPU](worker_original/logs/13-gemma4-e2b-ud-q4-k-xl--cpu.log) · [Log Qwen/CPU](worker_original/logs/portable-unsloth-qwen35-4b-q4-k-m--cpu.log)

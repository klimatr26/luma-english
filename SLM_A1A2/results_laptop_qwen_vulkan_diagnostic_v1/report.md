# Diagnóstico de carga de Qwen3.5 4B en la Quadro P1000

18 de noviembre de 2026, hora de Ecuador continental. La descarga completa de pesos a GPU es la condición que reproduce el fallo observado. Con el mismo GGUF en la misma Quadro, mover a CPU 70,33 MiB de pesos de cualquiera de dos bloques distintos permitió cargar el contexto y ejecutar una generación corta.

## Experimento

Se usó el mismo GGUF Q4_K_M, SHA-256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`, y se cotejaron las siete DLL del manifiesto b12359. Una sonda C++ enlazada con las bibliotecas de importación de la compilación existente llamó a la API pública de llama.cpp y verificó las rutas de las DLL efectivamente cargadas. Cada escenario arrancó en un proceso nuevo, seleccionado por PCI `0000:01:00.0`, con contexto 2048 y plazo de 85 s. En cargas exitosas se hizo prefill de 12 tokens y ocho pasos de decode greedy sobre texto sintético. La sonda mide funcionamiento técnico con un prompt corto.

| Variante en orden de ejecución | Pesos en búfer Vulkan (MiB) | VRAM global al pico (MiB) | Resultado |
|---|---:|---:|---|
| 16/33 capas, `mmap` | 1484,92 | 2053 | Carga y 8 pasos. Carga 2,95 s |
| 33/33 capas, lectura por bloques con transferencias asíncronas confirmadas | 2603,50 | 2606 | `ErrorDeviceLost` durante la carga |
| 32/33 capas, `mmap`, primer bloque en CPU | 2533,17 | 3159 | Carga y 8 pasos. Carga 3,91 s |
| 33/33 capas, `mmap`, bloques de subasignación limitados a 512 MiB | 2603,50 | 2606 | `ErrorDeviceLost` durante la carga |
| `mmap`, pesos del segundo bloque forzados a CPU, primer bloque elegible para GPU | 2533,17 | 3161 | Carga y 8 pasos. Carga 3,89 s |

La Quadro inició todas las variantes con 0 MiB de uso global y un presupuesto libre informado por el backend de 3617 MiB. Los picos de temperatura de GPU estuvieron entre 53 y 55 °C. En el último escenario llama.cpp sigue anunciando 33/33 capas porque se solicitó la colocación completa. La anulación de pesos se verifica por el búfer de CPU de 70,33 MiB y la reducción correspondiente en Vulkan. El GGUF atribuye exactamente 73 747 200 bytes de pesos a cada uno de los dos bloques.

## Qué quedó acotado

- **El fallo está en la transferencia de pesos.** El código imprime el número de capas y tamaño de los búferes antes de leer y copiar los tensores. Los dos fallos de la prueba anterior y las dos nuevas cargas completas fallidas devolvieron `vk::Queue::submit: ErrorDeviceLost` en ese tramo, antes de crear el contexto o ejecutar cómputo del modelo. [Prueba anterior](../results_laptop_resources_v1/report.md) · [Ruta de carga de llama.cpp](../tools/llama.cpp/llama.cpp-b1b770d90d94cad9e9ea5b993bdbc383a522fb28/src/llama-model.cpp#L2144)
- **Importa la colocación del conjunto de pesos.** Reducir el búfer de pesos en 70,33 MiB permitió cargar con dos colocaciones distintas. El primer bloque puede estar en la GPU cuando el segundo queda en CPU. La carga híbrida exitosa llegó a 3161 MiB de VRAM global al incluir contexto y cómputo. La cifra de 2606 MiB en el fallo describe el pico observado en esa fase. Cambiar la ruta de lectura o bajar el tamaño de los bloques de subasignación manteniendo toda la colocación en GPU reprodujo el fallo.
- **El motivo interno por el que se pierde el dispositivo sigue abierto.** El código Vulkan puede indicar varios tipos de fallo. Los registros System y Application consultados no mostraron eventos coincidentes del controlador, WDDM o Windows Error Reporting. El canal operativo de DxgKrnl no estaba disponible para la consulta. La Quadro volvió a 0 MiB y respondió a `nvidia-smi`. Estos datos localizan el fallo sin confirmar un TDR ni un límite de VRAM total. [Consulta de Windows](windows_events.json) · [Semántica de pérdida de dispositivo en Vulkan](https://docs.vulkan.org/spec/latest/chapters/devsandqueues.html#devsandqueues-lost-device)

## Implicación para la app

El candidato práctico para este portátil es **Qwen con 32 de 33 capas en GPU**. Conserva el GGUF y usa el parámetro normal de capas, con la salida en GPU. En esta sonda completó prefill y ocho pasos en 1,30 s desde el primer decode. La medición usa un prompt de 12 tokens, por lo que la latencia de la tarea de escritura y la estabilidad durante sesiones largas todavía requieren validación.

El puente actual fuerza 0 capas en CPU o descarga completa en Vulkan. Si se expone el número de capas, la app puede intentar una carga híbrida con el mismo Qwen antes de pedir otra descarga. El caso también sugiere qué debe medir una sonda previa a la descarga: la transferencia de pesos al tamaño de búfer previsto, además del presupuesto de memoria. [Puente actual](../cross_demo/native/src/writing_llama_bridge.cpp#L205)

## Evidencia

Cada carpeta conserva la solicitud, hashes, salida de progreso, log nativo y telemetría. Los primeros cuatro escenarios corresponden al ejecutable construido de `probe_initial.cpp`. El último usa `probe.cpp` con el parámetro opcional para forzar los pesos de un bloque a CPU. Ambos enlazan las mismas DLL verificadas.

- [16 capas, mmap](16-layers-mmap/) · [Carga completa, lectura por bloques](full-buffered/) · [32 capas, mmap](32-layers-mmap/)
- [Carga completa, subasignación de 512 MiB](full-mmap-smaller-blocks/) · [Pesos del segundo bloque en CPU](full-mmap-block1-cpu/)
- [Sonda inicial](probe_initial.cpp) · [Sonda con anulación de pesos](probe.cpp) · [Runner](run_probe.py)

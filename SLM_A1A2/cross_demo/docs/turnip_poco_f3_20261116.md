# Mesa Turnip en el POCO F3

16 de noviembre de 2026, UTC−5. Diagnóstico de inferencia local en el POCO F3 (`alioth`), Android 13/API 33, firmware `V816.0.5.0.TKHMIXM`, kernel 4.19.157 y GPU Adreno 650. La app instalada era Writing Lab 0.1.2. Las pruebas se ejecutaron desde ADB en procesos independientes con la misma revisión b12359 de llama.cpp y el mismo plugin Vulkan ARM64 que se prepararon para Writing Lab 0.1.4. [Compilación b12359 y ensayo anterior en el F8 Pro](llama_cpp_turnip_20261113.md).

## Controlador y cómputo

| Prueba | Resultado |
|---|---|
| Loader y GPU con el controlador de fábrica | Loader Vulkan 1.3.0, GPU Vulkan 1.1.128. Vulkan explícito devolvió `WG_ERROR_BACKEND_UNAVAILABLE` (−2) y Auto eligió CPU. |
| Enumeración con el loader Khronos 1.4.368 y Mesa Turnip 26.2.7 | GPU física `Turnip Adreno (TM) 650`, Vulkan 1.3.354, `DRIVER_ID_MESA_TURNIP`. |
| Cómputo Vulkan con Turnip | Un shader escribió 32 enteros comprobados por la CPU. Pasó al asociar la fence al envío del shader y al asociarla a un envío vacío posterior. |
| Operaciones GGML con Turnip | El binario upstream `test-backend-ops` pasó 60/60 casos de `SSM_CONV` y 21/21 casos compatibles del subconjunto `MUL_MAT` Q4_K × F32 elegido. El backend omitió otras seis formas de ese subconjunto que informó como no compatibles. |

La sonda de cómputo y las operaciones de GGML confirman que Turnip ejecuta trabajo real en la GPU del F3. El criterio para habilitar esa vía en Writing Lab requiere además una inferencia completa. [Mesa para Android con KGSL](https://docs.mesa3d.org/android.html), [fuente de las pruebas de GGML en b12359](https://github.com/ggml-org/llama.cpp/blob/b1b770d90d94cad9e9ea5b993bdbc383a522fb28/tests/test-backend-ops.cpp).

## Inferencia con LFM2.5 1.2B Q4_K_M

Se reutilizó el ejemplo incorrecto A1 empleado en el F8 Pro. El ensayo usa contexto 2048, semilla 42, límite de 512 tokens de salida, gramática JSON y la misma política de thinking y muestreo. El modelo de 730.895.168 bytes se cotejó en el ordenador y en el teléfono con SHA-256 `b1b3de114215d9507409a662a501a631095a479a419584e8a2ded6304b19b4f5`.

| Configuración | Resultado |
|---|---|
| Auto, controlador de fábrica | CPU `android_armv8.2_2`. Terminó en `stop` con 301 tokens de entrada y 48 de salida en **4,69 s** de generación. El parser marcó `INCONSISTENT` porque el modelo cambió el texto a la vez que lo declaró correcto. |
| Turnip, valores de la app, 17/17 capas | El puente cargó los pesos y reservó un búfer de cómputo GPU de 146,02 MiB. Tras 1 min 46 s, el proceso seguía en `adreno_drawctxt_wait` y se terminó con SIGTERM. |
| Turnip, envíos serializados, 17/17 capas | Límite de 45 s sin respuesta completa. |
| Turnip, fusión y asincronía desactivadas, 17/17 capas | Límite de 40 s sin respuesta completa. |
| Turnip, Flash Attention desactivado, 17/17 capas | Límite de 45 s sin respuesta completa. |
| Turnip, microlote de 64 tokens, 17/17 capas | Terminó de enviar el prompt y registró el primer token muestreado. Límite de 40 s sin respuesta completa. |
| Turnip, 8/17 capas en GPU y las demás en CPU | El primer intento registró 96 tokens muestreados al detenerse a los 45 s. La repetición con un límite de 240 s agotó los 512 tokens en **206,92 s** de generación y dejó el objeto incompleto. El parser marcó `INVALID_JSON`. |

Los tiempos de generación excluyen la carga del GGUF. Los límites de las ejecuciones externas incluyen la carga. La variante de 8 capas registró **2,61 tokens/s** en decodificación, frente a **24,00 tokens/s** en la ejecución de CPU. Son mediciones puntuales con distinta longitud de salida. El punto de espera del primer intento indica que el hilo esperaba un hito de GPU en KGSL. La operación concreta que originó la espera queda por identificar. [Implementación de `adreno_drawctxt_wait` en un kernel Android 4.19](https://android.googlesource.com/kernel/msm/+/refs/heads/android-msm-redbull-4.19-s-beta-3/drivers/gpu/msm/adreno_drawctxt.c).

## Reproducción y evidencia

Se reutilizaron los paquetes verificados del ensayo del F8 Pro. El SHA-256 de `libvulkan_freedreno.so` fue `2437ba2e10231b47e6712cc4f035b8dbaf19ecc679be5981e2e885e325be7272` y el del plugin `libggml-vulkan.so` fue `95880109156f24f826259e5c2504deace910c45dbe5e746245422f0da4091283`. Un entorno privado por proceso eligió el loader y su ICD con `LD_LIBRARY_PATH` y `VK_DRIVER_FILES`. Las variantes de Flash Attention, microlote y ocho capas se compilaron en copias temporales del puente de Writing Lab. Usaron las mismas bibliotecas de llama.cpp sin parches.

Los comandos, entradas, estados de salida, código de la sonda de cómputo, logs nativos y respuestas obtenidas se guardaron en `SLM_A1A2/logs/cross_demo/f3_turnip_20261116/`. Las pruebas de operaciones y de modelo usaron datos sintéticos de diagnóstico. Se retiró del teléfono el directorio temporal y se verificó la integridad de los 24 artefactos históricos de Fase 1.

## Criterio para Writing Lab

Para esta combinación de GPU, controlador y modelo, CPU es la opción práctica. En el F8 Pro hubo generaciones completas con Turnip, incluido Qwen 3.5 4B Q4_K_M con JSON utilizable. El contraste justifica comprobar el controlador y las capacidades reales y ejecutar una inferencia acotada antes de habilitar una ruta Vulkan experimental. Conviene registrar el modelo, la cuantización, el controlador efectivo y el resultado de esa prueba.

La siguiente validación de integración puede hacerse en un APK de diagnóstico con un servicio en un proceso privado de la aplicación. Así se puede comprobar el loader en el entorno real de Android, terminar el proceso si vence el plazo y usar CPU con un motivo visible. La política se basaría en el resultado de la prueba y en las capacidades del controlador. [Procesos privados para servicios en Android](https://developer.android.com/guide/topics/manifest/service-element#proc), [ensayo con Turnip en el F8 Pro](llama_cpp_turnip_20261113.md).

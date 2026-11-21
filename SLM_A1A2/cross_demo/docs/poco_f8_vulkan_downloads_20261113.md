# Writing Lab 0.1.3 en el POCO F8 Pro

El 13 de noviembre de 2026 se probó Writing Lab en el POCO F8 Pro 2510DPC44G con Android 16, Snapdragon SM8750 y Adreno 830. La GPU reportó Vulkan 1.3.284. El controlador propietario de Qualcomm era 0800.71 (`0x80320047`), compilación `208ca19915`, con compilador de shaders `E031.47.18.49`. El motor de la demo se compiló contra llama.cpp b11457, commit `5ad1c5da0ad7f6176256b823925aad19134f0263`.

## Fallo de Vulkan y respuesta de la aplicación

Se ejecutó una consigna sintética de Writing A1 mediante `native/tools/inference_smoke.cpp` y las bibliotecas instaladas de la versión 0.1.2. El proceso de diagnóstico se ejecutó desde ADB. LFM2.5 1.2B Q4_K_M y Qwen 3.5 4B Q4_K_M de Unsloth cargaron en `Vulkan0`. En ambos, el controlador rechazó `mul_mat_vec_q4_k_f32_f32` durante la generación con `vk::Device::createComputePipeline: ErrorUnknown`. llama.cpp recibió un reporte del mismo error en otros dispositivos Adreno 830. La conversación documenta que la hipótesis inicial sobre la versión del compilador de shaders fue retirada. [Incidencia de llama.cpp #28635](https://github.com/ggml-org/llama.cpp/issues/28635).

Desactivar MMVQ produjo el mismo error. Una compilación experimental encaminó Q4_K a la multiplicación de matrices general de Vulkan y llegó a `ErrorDeviceLost`. Además, una llamada de diagnóstico del propio controlador, `vkGetDeviceFaultInfoEXT`, provocó SIGSEGV. Omitir esa llamada y probar sin Flash Attention reveló `ErrorDeviceLost` durante el cálculo. Estos ensayos se ejecutaron en procesos separados. La entrega usa el plugin Vulkan de 0.1.2.

La versión 0.1.3 detecta la combinación probada de fabricante, GPU y controlador propietario antes de inicializar GGML Vulkan. **Auto Vulkan/CPU** carga el modelo con CPU y muestra el motivo. Al elegir **Vulkan** explícitamente, la carga devuelve un error con el diagnóstico y la alternativa disponible. Otros controladores continúan sujetos a la comprobación de la versión de Vulkan y a la detección habitual de llama.cpp.

### Comprobaciones del motor en el teléfono

Se usó contexto 2048, semilla 42, JSON guiado y thinking desactivado donde la plantilla lo admite. Los tiempos son de una sola generación por comprobación y corresponden a sus respectivos prompts y salidas.

| Modelo y selección | Resultado | Tiempo de generación |
|---|---|---:|
| LFM2.5 1.2B Q4_K_M, Vulkan explícito | Rechazo durante la carga, estado `-2` | — |
| LFM2.5 1.2B Q4_K_M, Auto | CPU, JSON sintácticamente válido con veredicto incoherente respecto al texto editado | 2,66 s |
| Qwen 3.5 4B Q4_K_M de Unsloth, Auto | CPU, JSON válido con `is_correct=false` y corrección de `wakes` a `wake` | 27,15 s |

El motor seleccionó `libggml-cpu-android_armv8.6_1.so`. Qwen procesó 714 tokens de entrada y generó 155. En la aplicación instalada, el usuario cargó el Qwen recuperado, eligió el ejemplo incorrecto y solicitó una evaluación. La interfaz mostró «JSON válido y contrato correcto», la marca de error y la corrección `wakes → wake`. Informó 27,6 s en total, 16,6 s de procesamiento de la entrada, 155 tokens de salida y 14,3 tokens/s de decodificación. Los registros de diagnóstico local están en `SLM_A1A2/logs/cross_demo/v013/`. La evaluación mediante GPU sigue pendiente en esa versión del controlador.

## Recuperación y persistencia del GGUF

El Qwen de Unsloth seguía en el almacenamiento temporal de `DownloadManager` bajo `Android/data/org.kevinlima.writinglab/files/Download`. Coincidía con la entrada `Q4_K_M` del catálogo tanto en tamaño (2.740.937.888 bytes) como en SHA-256 (`00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`). En 0.1.2, una descarga que terminaba fuera de la vista quedaba en esa ubicación hasta volver a pulsar el botón de descarga. Android documenta que su limpieza puede retirar descargas no visibles tras siete días sin modificaciones. [Android DownloadManager.Request](https://developer.android.com/reference/android/app/DownloadManager.Request#setVisibleInDownloadsUi(boolean)).

En 0.1.3, la notificación de finalización del sistema programa un trabajo que verifica el tamaño, la cabecera GGUF y el SHA-256. Al abrir la app se vuelven a buscar trabajos completos. **Cargar modelo** también puede recuperar la descarga correspondiente. La aplicación escribe en un archivo temporal del almacén privado, publica el GGUF mediante un cambio de nombre y solo después retira el temporal de `DownloadManager` y su ticket. Si se interrumpe la verificación o la copia, el trabajo completo queda disponible para otro intento. [Almacenamiento permanente de la aplicación en Android](https://developer.android.com/training/data-storage/app-specific#internal-access-files).

La actualización se instaló por ADB sobre la versión 0.1.2. Al abrirla, el trabajo verificó y guardó el Qwen ya descargado. Después se comprobó que la interfaz lo mostraba disponible y lo cargaba desde `files/models/portable_unsloth_qwen35_4b/Qwen3.5-4B-Q4_K_M.gguf` con backend efectivo CPU. Antes de finalizar el trabajo se hizo una copia verificada del archivo a `SLM_A1A2/models/portable_unsloth_qwen35_4b/Qwen3.5-4B-Q4_K_M.gguf` en el ordenador. Guardar modelos en `files/models` los preserva al limpiar la caché ordinaria o instalar una actualización. Borrar los datos de la aplicación o desinstalarla puede retirar sus archivos privados.

## Entrega

APK de desarrollo firmado `artifacts/android-0.1.3/org.kevinlima.writinglab-Signed.apk`, versión 0.1.3, código 4, ARM64 y x86_64. Se comprobaron la firma, la alineación de 16 KiB, las bibliotecas nativas del paquete y la coincidencia del SHA-256 del APK instalado. La prueba por ADB se completó con la configuración USB que ya tenía el teléfono.

| Artefacto | SHA-256 |
|---|---|
| APK 0.1.3 (185.815.060 bytes) | `bc6e1675594b486f1433954e8f0655ee0d76d21d4bfad1b34508d5b113590627` |
| Puente ARM64 | `6a3cb1b0421feeea52aaa9b87266510078c01052fb9039b7c85021048f283380` |
| Puente x86_64 | `81debea57c89c8b2e072a0a7dae83c1c6066b52a8c6d055a414f5266b988f8fd` |
| Plugin Vulkan ARM64 | `0ef0c45eb1f23dfc91c48f477814bae2abac9ef46876e740e87339f722078f9d` |

Pasaron 26 pruebas compartidas y cuatro de interfaz. Las dos pruebas nuevas cubren la recuperación sin ticket y la conservación del trabajo tras interrumpir la publicación. El emulador reportó almacenamiento insuficiente para la prueba de descarga y actualización. La recuperación tras actualizar y la evaluación en la interfaz se comprobaron en el POCO. La comprobación de integridad validó los 24 artefactos de la Fase 1 y la auditoría de evaluación confirmó los 93 archivos de entrada de Git y 76 hashes de salidas.

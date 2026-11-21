# Vulkan en la aplicación Windows Forms

Fecha: 2026-11-09. Esta entrega incorpora una alternativa a CUDA en el prototipo tecnológico de Writing A1/A2. Las pruebas descritas son generaciones sintéticas con un ejercicio nuevo del catálogo de demostración; no son nuevas observaciones de los benchmarks ni validan la calidad de los prompts revisados.

## Decisión y procedencia

Se eligió la distribución **oficial Windows x64 Vulkan de llama.cpp b11457**, del mismo commit que el runtime CUDA preservado: `5ad1c5da0ad7f6176256b823925aad19134f0263`. Mantener el commit reduce cambios simultáneos en la integración, aunque dos backends pueden producir resultados numéricos y textos distintos con el mismo modelo y semilla. No se atribuye una diferencia de calidad al backend con estas pruebas.

Fuente: [release b11457](https://github.com/ggml-org/llama.cpp/releases/tag/b11457), archivo `llama-b11457-bin-win-vulkan-x64.zip`. El SHA-256 del ZIP, `d01301582c711a69b9747b5984710d6ca99e57d95f680d3d33753cec570b4cb6`, coincide con el digest publicado por GitHub. El [manifiesto del paquete](../manifests/demo_vulkan_runtime_20261109.json) conserva procedencia, bytes y hashes de los 52 archivos extraídos. Su huella fijada en C# es `0a88187f51d3d37ce6337372740d0911bca177690073fce48f2e917382e3bec2`.

Se conserva el paquete completo, incluidos 14 plugins CPU y la licencia LLVM/OpenMP; no es un despliegue mínimo obtenido eliminando herramientas. No contiene DLL CUDA ni distribuye `vulkan-1.dll`: el loader/driver Vulkan compatible debe proporcionarlo el sistema. El [build guide fijado](https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/docs/build.md) explica la compilación Vulkan y la selección de dispositivos.

| Medida comparable | Bytes | MiB (2²⁰ bytes) |
|---|---:|---:|
| Runtime CUDA preservado, 54 EXE/DLL y una licencia | 745.680.493 | 711,14 |
| Runtime Vulkan, 51 EXE/DLL y una licencia | 94.916.893 | 90,52 |
| ZIP Vulkan retenido para procedencia | 33.377.746 | 31,83 |

La reducción de archivos extraídos es **650.763.600 bytes, 620,62 MiB, aproximadamente 87,3 %**. La carpeta local Vulkan ocupa además el ZIP retenido: 128.294.639 bytes. Las cifras excluyen GGUF, aplicación C# y .NET Desktop Runtime. Los pesos siguen ocupando varios GB; Vulkan reduce el componente de ejecución, no el tamaño del modelo. El informe previo de viabilidad contaba 55 archivos CUDA como EXE/DLL; uno es la licencia, de ahí la precisión de esta tabla.

## Comportamiento implementado

La nueva publicación está en `demo/publish/vulkan_20261109/`. La guía de uso es [demo/README.md](../demo/README.md).

| Selección | Decisión y límites |
|---|---|
| **Auto Vulkan/CPU**, inicial | Verifica modelo y paquete; consulta `--list-devices`; elige el primer `VulkanN` informado. Si no aparece o falla técnicamente el sondeo/arranque, intenta CPU una vez. |
| **Vulkan** | Exige dispositivo Vulkan y evidencia positiva de offload. Un fallo se presenta al usuario. |
| **CPU** | No necesita un dispositivo Vulkan enumerado; usa el mismo paquete con `--device none -ngl 0 --no-kv-offload --no-op-offload`. |
| **CUDA anterior** | Conserva el runtime original, la API previa y su validación del ejecutable. Su selección histórica no incorpora una medición nueva de offload. |

Antes de iniciar se comprueban tamaño/SHA-256 del GGUF, manifiesto fijado y todos sus archivos. Se rechazan DLL/EXE extra y enlaces dentro del paquete. La descarga/adquisición está separada de la carga. Los procesos hijos usan el directorio del paquete verificado y un entorno de búsqueda de DLL acotado; no se alteran drivers ni variables globales.

Vulkan se solicita mediante `--device VulkanN -ngl 999`. La aplicación espera `/health` estricto, comprueba que el puerto loopback pertenece al PID propio y lee el resumen real `offloaded X/Y layers to GPU` en el log de esa carga. Solo declara Vulkan activo si X es positivo. La asignación de capas no significa que todas las operaciones del grafo ocurran en GPU. La UI muestra backend efectivo y el registro conserva dispositivo lógico, capas y motivo de fallback. Las sesiones usan `writing_local_demo/1.2` con `runtime_backend`.

El fallback solo ocurre **antes de la generación**. No se cambia el modelo, cuantización, contexto o prompt para que una respuesta mejore. JSON inválido, una explicación incorrecta o un fallo posterior al envío no provocan una repetición en CPU. Un HTTP 429 es terminal. Cancelación y fallos de integridad tampoco se reinterpretan como falta de GPU. Se conserva la parada exclusiva del proceso hijo, puertos 18400–18499 y una sola instancia de modelo.

Se mantienen contexto 4096, máximo 512 tokens, semilla 42, parámetros por familia, plantillas nativas y thinking desactivado (`--reasoning off`, presupuesto 0, y `enable_thinking=false` donde existe control nativo). El harness usa explícitamente `benchmark-base`, sin cambiar las instrucciones al observar el texto de salida. Los perfiles derivados de la revisión humana siguen pendientes de validación empírica.

## Incidencias preservadas

1. El primer intento de cinco familias detectó una incompatibilidad de compartición de archivo: el lector C# del log impedía leerlo mientras llama.cpp lo mantenía abierto para escritura. Las cargas Vulkan llegaron a ejecutarse, pero la comprobación de offload falló y Auto pasó a CPU. Se recibieron cinco generaciones CPU. Se conservó `logs/writing_demo/vulkan_auto_smoke_20261109.json`; no se presenta como aceptación Vulkan.
2. Tras endurecer el inventario, una compilación intermedia trató la licencia sin extensión como si tuviera que ser una DLL/EXE. El segundo intento fue rechazado durante la verificación: cinco fallos, **cero cargas y cero generaciones**. Se conservó `vulkan_auto_smoke_fixed_20261109.json`. El validador final comprueba los 52 hashes y compara el inventario binario solo con los 51 EXE/DLL.
3. La lectura final usa `FileShare.ReadWrite | FileShare.Delete`; una prueba mantiene un escritor abierto y comprueba la lectura. Otra incluye la licencia y rechaza una DLL adicional. Las repeticiones se debieron a estos defectos técnicos y conservan archivos separados; no se eligieron respuestas por calidad.

## Android

Vulkan es una ruta viable para investigar aceleración móvil, pero esta entrega es Windows x64. WinForms y la supervisión Win32 del servidor no son portables directamente a Android. Se propone un contrato de inferencia común y una implementación Android nativa arm64 mediante NDK/JNI, empezando con CPU y añadiendo Vulkan sujeto a capacidades del dispositivo. El código b11457 exige Vulkan 1.2; para la ruta prevista se comprobarían Android API 33+ y driver/capacidades reales, sin deducir compatibilidad solo por versión de Android.

Se necesita otra UI, administración del ciclo de vida/almacenamiento y pruebas físicas de RAM, consumo, temperatura y drivers. No se compiló un APK ni se probó un teléfono. El razonamiento y fuentes del port están en [las notas Android](vulkan_android_integration_notes_20261109.md), que son una revisión de fuentes previa a esta integración y mantienen su checklist de investigación.

## Conservación experimental

Se verificaron sin diferencias los 24 artefactos de Fase 1, los 164 archivos fuente y 76 derivados del audit de evaluación v2, y 93 entradas Git originales. No se modificaron el manifiesto experimental, los pesos, CUDA, los benchmarks, los RAW anteriores, los resultados de evaluación ni la revisión humana importada. No se creó ni consultó el test final, ni se configuró remoto o publicación externa.

Los registros técnicos nuevos permanecen en `logs/writing_demo/`, fuera de Git; el registro de verificación de esta entrega conserva sus hashes y un resumen de resultados. Su objetivo es comprobar la ruta tecnológica de demostración, no recalcular la clasificación de los modelos.

## Resultados técnicos finales

Equipo: Windows x64, RTX 3070 (8 GiB nominales), Ryzen 5 5600X, 16 GiB RAM. Se probaron **las 13 configuraciones activas**, una generación sintética cada una, secuencialmente, con Auto Vulkan/CPU. Todas seleccionaron **Vulkan0**, tuvieron offload positivo y terminaron la petición HTTP. Los logs confirman contexto efectivo **4096**. No hubo fallback en esta matriz final.

Ejercicio: `demo-a1-my-day`, A1; consigna `Write two short sentences about your morning routine.`; entrada `I wakes up at seven. I eat breakfast at home.`. Es un ejemplo nuevo de la demo. Las cinco configuraciones Q4 principales están en `vulkan_auto_smoke_acceptance_20261109.json`; las ocho restantes, en `vulkan_quantization_smoke_20261109.json`.

| Configuración | Capas offload | Buffer de pesos Vulkan (MiB) | Estado del parser | Tiempo de petición (s) |
|---|---:|---:|---|---:|
| MiniCPM5 2B F16 | 43 | 4290,66 | STRICT | 6,446 |
| MiniCPM5 2B Q8_0 | 43 | 2279,73 | STRICT | 6,130 |
| MiniCPM5 2B Q4_K_M | 43 | 1340,64 | STRICT | 2,485 |
| LFM2.5 1.2B BF16 | 17 | 2232,50 | INCONSISTENT | 6,229 |
| LFM2.5 1.2B Q8_0 | 17 | 1186,25 | INCONSISTENT | 0,291 |
| LFM2.5 1.2B Q4_K_M | 17 | 694,76 | INCONSISTENT | 1,089 |
| Qwen3.5 4B Q8_0 | 33 | 4264,29 | STRICT | 3,326 |
| Qwen3.5 4B Q4_K_M | 33 | 2572,86 | STRICT | 25,505 |
| Gemma 4 E2B QAT Q4_0 | 36 | 1341,76 | STRICT | 3,422 |
| Gemma 4 E2B UD-Q4_K_XL | 36 | 1223,90 | RECOVERED | 18,798 |
| Gemma 4 E2B UD-Q2_K_XL | 36 | 809,83 | INVALID_JSON | 7,958 |
| LFM2.5 2.6B Q8_0 | 31 | 2733,75 | RECOVERED | 1,369 |
| LFM2.5 2.6B Q4_K_M | 31 | 1589,03 | RECOVERED | 1,577 |

**Interpretación:** 6 salidas estrictas, 3 recuperadas, 3 incoherentes y 1 JSON inválido. `RECOVERED` requiere extraer JSON de una envoltura; `INCONSISTENT` indica contradicciones entre campos del contrato. Son estados observados del formato, sin calificación lingüística nueva. Se conserva el RAW y no se ajustaron parámetros ni se repitió una respuesta por estos estados. La interfaz muestra advertencias en esos casos.

Los tiempos incluyen el procesamiento del prompt y pueden incluir inicialización de kernels/shaders; no incluyen hashing/carga. Se guardan como diagnóstico de una petición, sin repeticiones estadísticas ni control del estado de caché. **No permiten concluir que Vulkan sea más rápido que CUDA o que una cuantización sea más rápida que otra.** El buffer de pesos no es un pico de VRAM total: faltan KV, cómputo, driver y otras aplicaciones. El offload acredita asignación de capas y generación con ese backend; no se midió la fracción de operaciones ejecutadas en GPU.

### CPU y entorno final

`vulkan_hidden_cpu_smoke_20261109.json` contiene una generación LFM1.2 Q4 con `GGML_VK_VISIBLE_DEVICES=""` definido solo en sondeo y servidor hijo. Auto detectó cero dispositivos, seleccionó CPU con 0 capas offload y terminó la petición en 2,575 s; el parser indicó INCONSISTENT. El motivo queda explícito como **simulación diagnóstica**. Esta prueba no representa un sistema sin loader/driver ni un teléfono Android.

En la revisión final se retiró la variable heredada `GGML_BACKEND_PATH`: upstream la interpreta como un archivo de plugin externo, no una carpeta. Los binarios ya habían cargado correctamente por su escaneo estándar junto al ejecutable. El entorno final usa directorio de trabajo y PATH del paquete verificado, sin ese override. Se repitieron **carga/health/offload**, sin petición de chat, con el código final: Vulkan 17 capas (`vulkan_final_env_load_20261109.json`) y Auto→CPU 0 capas con GPUs ocultas (`cpu_final_env_load_20261109.json`). El warmup interno normal de llama.cpp permanece activo.

En total se enviaron **19 peticiones nuevas de generación técnica: 13 Vulkan y 6 CPU**, incluyendo las cinco CPU del primer intento con el defecto del log. Se conservan además cinco rechazos de preflight sin carga y dos comprobaciones finales sin petición de chat. No se suman estas observaciones a los resultados académicos de 40/120 casos.

### Comprobaciones de software y reproducción

- Compilación Release y publicación Windows Forms: correctas, sin advertencias ni errores en la compilación final. SDK estable .NET 10.0.403 mediante `global.json`; requiere .NET 10 Desktop Runtime.
- **207** pruebas Python de `SLM_A1A2/scripts`: pasan. **18** pruebas Python de `demo/scripts`: pasan, incluidas 10 de adquisición/restauración Vulkan mediante fixtures offline.
- **18/18** comprobaciones C# del runtime: pasan; cubren selección, ausencia de GPU, fallback único de arranque, CPU forzada, cancelación, integridad, entorno, lectura compartida del log, HTTP 429 y ausencia de reenvío de generación. Las suites FeedbackTests, AssetTests y PromptTests también pasan.
- Se cotejaron **53 hashes** del paquete Vulkan (52 extraídos y ZIP) y los **11** activos del manifiesto original del runtime. La restauración `--restore-pinned` conserva el manifiesto y se verificó con fixtures; no se hizo una segunda descarga real innecesaria.
- Comprobación visual de la aplicación nativa: selector inicial, cuatro opciones y cambio a CPU; se verificó la publicación final sin cargar modelos a través de la UI. Las pruebas reales de carga/generación usan el mismo `WritingDemo.Core` mediante el harness. [Captura del selector](assets/demo_vulkan_selector_20261109.jpg).

Para compilar sin reemplazar las versiones anteriores, desde `SLM_A1A2/demo`:

```powershell
dotnet publish WritingDemo.WinForms/WritingDemo.WinForms.csproj -c Release --no-self-contained -o publish/vulkan_20261109
dotnet run --project WritingDemo.RuntimeTests/WritingDemo.RuntimeTests.csproj -c Release
python -m unittest discover -s scripts -p "test_*.py"
```

Para una **nueva** prueba técnica de las 13 configuraciones, separada de las pruebas unitarias y de los benchmarks:

```powershell
$catalogIds = ((Get-Content model_sources.json -Raw | ConvertFrom-Json).models.config_id) -join ','
dotnet run --project WritingDemo.BackendSmoke/WritingDemo.BackendSmoke.csproj -c Release -- --execute --backend AutoVulkanCpu --models $catalogIds
# Una generación con CPU tras ocultar dispositivos solo al hijo:
dotnet run --project WritingDemo.BackendSmoke/WritingDemo.BackendSmoke.csproj -c Release -- --execute --backend AutoVulkanCpu --models 09-lfm25-12b-q4-k-m --hide-vulkan-devices
```

Estos comandos generan evidencias nuevas con nombre único. `--load-only` omite la petición de chat. La cancelación y HTTP 429 conservan su incidencia y detienen la secuencia. El [registro de verificación](../demo/verification_vulkan_20261109.json) indexa resultados, archivos, hashes y límites; los errores iniciales no se borraron ni se sustituyeron por la aceptación.

Quedan pendientes otras GPU/drivers, la ausencia física de loader, rendimiento sostenido y memoria pico, empaquetado mínimo/instalador y la implementación Android. La viabilidad demostrada corresponde a este equipo Windows y a las cargas sintéticas registradas.

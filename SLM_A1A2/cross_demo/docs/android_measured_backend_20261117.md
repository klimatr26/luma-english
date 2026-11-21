# Android 0.1.5 y selección medida de Vulkan

17 de noviembre de 2026, UTC−5.

Writing Lab ejecuta el puente b12359 de llama.cpp en un proceso hijo de la app. El proceso recibe las operaciones de carga y generación mediante JSON por entrada estándar y devuelve la respuesta por salida estándar. El ejecutable PIE se empaqueta como `libwriting_worker.so` y Android lo extrae a `nativeLibraryDir`. Ese directorio permite ejecutar el binario en las versiones recientes de Android. [Directorio de bibliotecas nativas](https://developer.android.com/guide/topics/manifest/application-element#extractNativeLibs), [restricciones de ejecución desde directorios de datos](https://developer.android.com/about/versions/10/behavior-changes-10#execute-permission).

La interfaz se comunica con el proceso mediante `AndroidWorkerEngine`. Cada petición tiene plazo y cancelación. Una interrupción termina el proceso propio. La app puede volver a cargar el modelo en otro proceso. El límite de generación normal es 120 segundos. El resultado técnico fallido se muestra en la interfaz y una ruta Vulkan que falla queda invalidada para la siguiente carga automática.

## Controlador y alcance

En ARM64 con API 28 o posterior, la comprobación de `/dev/kgsl-3d0` identifica la ruta KGSL. En esa ruta se usa el loader de Khronos 1.4.368 con Mesa Turnip 26.2.7 y se confirma `DRIVER_ID_MESA_TURNIP` antes de cargar el modelo. Se fijan `LD_LIBRARY_PATH` y `VK_DRIVER_FILES` en el entorno del proceso hijo. Las otras GPU se evalúan con el loader del sistema. La decisión usa las capacidades y mediciones y queda ligada al controlador observado. [Interfaz de drivers del loader de Khronos](https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderDriverInterface.md).

El bundle deriva de los paquetes de Termux que se verificaron en el ensayo del 13 de noviembre. Incluye las dependencias de Mesa, su loader y una biblioteca C++ compatible en el proceso aislado. `native/TURNIP_MANIFEST.json` fija sus bytes y hashes. Se incluyen los avisos de terceros dentro del APK. El SHA-256 del bundle determinista es `085805213ad379b24b6221b2675aa95b6bb7adee7dfd13ba88bd15a481b90748`. El worker tiene SHA-256 `12963d89c0f146279f3a739149a7d7e564d99043d67b2de07316958aea25c8c8`. [Procedencia del runtime](llama_cpp_turnip_20261113.md), [manifiesto del controlador](../native/TURNIP_MANIFEST.json).

## Selección automática

La primera carga automática de cada combinación ejecuta un calentamiento y tres evaluaciones sintéticas con CPU, seguido del mismo protocolo con Vulkan. Usa una consigna A1 sobre la rutina diaria, el ejemplo `I wakes up at seven. I eat breakfast at home.`, el prompt y muestreo del modelo, contexto 2048, semilla 42 y hasta 512 tokens con la gramática JSON de la app.

Vulkan se selecciona cuando las tres evaluaciones terminan con `stop`, pasan el parser como `STRICT` o `RECOVERED` y el cociente entre la mediana de latencia CPU y la mediana Vulkan es al menos 1,15. CPU es la elección cuando falta evidencia o falla cualquiera de esas condiciones. El parser comprueba estructura y coherencia interna del veredicto. La revisión lingüística completa sigue siendo una tarea de evaluación del modelo.

El resultado se guarda en los archivos privados `backend-profiles/`. Su clave incluye el hash del GGUF, el prompt, los parámetros de muestreo, contexto, revisión de runtime, bundle del controlador y firmware. La carga siguiente reutiliza la decisión. Las opciones explícitas Vulkan y CPU permiten elegir manualmente. El deadline de Vulkan en la comparación es tres veces la mediana CPU, acotado entre 20 y 120 segundos.

Los plazos y la calibración se aplican a procesos individuales. La app usa un wakelock parcial durante carga y generación. Para estas mediciones se mantuvo la pantalla encendida por USB y se registró el ajuste previo para restaurarlo. En un intento inicial con la pantalla apagada, Android asignó al proceso hijo el grupo de CPU de fondo con un solo núcleo. Sus registros se conservaron y la comparación se repitió en primer plano.

## Ensayo en el POCO F8 Pro

Se instalaron builds temporales de diagnóstico sobre Writing Lab y se ejecutaron las operaciones con el UID de la aplicación. La actividad de diagnóstico se incluye mediante una propiedad de compilación y se excluye del APK de entrega. Las evaluaciones corresponden a ejemplos sintéticos de la demo. La configuración de hardware fue Adreno 830, Android 16 y firmware `OS3.0.302.0.WPKMIXM`.

El experimento conserva el RAW de cada calentamiento y muestra medida, los tiempos, los tokens y el estado del parser. Se hizo una evaluación adicional tras la selección de cada modelo. Los tiempos siguientes excluyen carga y compilación inicial de pipelines. La respuesta generada puede diferir por backend y por eso se registra también su longitud.

| Modelo Q4 | Mediana CPU (s) | Mediana Turnip (s) | Tokens CPU / Vulkan | Elección Auto |
|---|---:|---:|---:|---|
| Qwen 3.5 4B, Unsloth | 37,22 | 22,53 | 167 / 155 | Vulkan |
| MiniCPM5 2B | 48,48 | 6,80 | 90 / 48 | Vulkan |
| Gemma E2B UD-Q4_K_XL | 15,45 | 12,64 | 237 / 230 | Vulkan |
| LFM2.5 2.6B Q4_K_M | 15,42 | 13,04 | 190 / 204 | Vulkan |
| LFM2.5 1.2B Q4_K_M | 3,72 | 2,42 | 48 / 48 | CPU |

Qwen, MiniCPM, Gemma y LFM2.5 2.6B devolvieron `STRICT` en las tres medidas por backend y en la evaluación posterior. La menor latencia de Vulkan incluye diferencias en el texto generado. En MiniCPM, los tiempos CPU fueron 58,49, 48,48 y 26,99 s, por lo que la mediana describe estas tres ejecuciones. En LFM2.5 1.2B, Turnip completó el cálculo más rápido y produjo la misma contradicción de veredicto que CPU. Auto conservó CPU porque las respuestas Vulkan fueron `INCONSISTENT`.

Se comprobó que la segunda carga automática de Qwen reutiliza el mismo identificador y fecha de calibración, seguida de una evaluación `STRICT`. Se forzó un deadline de un milisegundo y una cancelación durante una generación CPU. En ambos casos se observó la interrupción y una carga posterior terminó otra generación en `stop`. Las comprobaciones de servicios pasaron 27/27 y las de estado de interfaz 4/4.

El [registro de mediciones](../manifests/android_measured_backend_20261117.json) incluye las tres muestras y las identidades de sus fuentes. La evidencia local completa está en `SLM_A1A2/logs/cross_demo/f8_app_20261117/`. El código de la actividad automatizada se compila únicamente con `WritingDiagnostics=true`.

## Entrega

APK `artifacts/android-0.1.5/org.kevinlima.writinglab-Signed.apk`, versión 0.1.5, código 6, ARM64 y x86_64, 196.061.102 bytes. SHA-256 `845c9b68762d9e3b5be9dde256f4dafd33d8b2147e976a40d9c681d007ffe458`. Se comprobó la firma del mismo certificado de desarrollo, la alineación de 16 KiB, el worker y el driver empaquetados y la exclusión de la actividad de diagnóstico.

Se instaló como actualización en el F8 Pro y se verificó el hash de su APK instalado. La actividad principal arrancó correctamente. Al terminar se restauró el ajuste original de pantalla por USB. Se retiraron las tres copias temporales de GGUF de `diagnostic-models/`, comprobando sus hashes antes de eliminarlas. Las copias importadas y verificadas permanecen en el almacenamiento privado permanente de modelos de la aplicación.

## Desarrollo de la aplicación final

El motor aislado y la política medida pueden reutilizarse en el proyecto Avalonia final. La selección depende del modelo y del controlador observado. El curso y su progreso pueden persistirse en SQLite, conservando el hash del modelo y la decisión de backend junto al historial de evaluaciones. La propuesta de curso está disponible en `docs/curso_demo/propuesta_curso.md`.

Las pruebas anteriores del F3 encontraron cómputo Vulkan funcional, pero un rendimiento y formato insuficientes con LFM1.2. Su ruta CPU continúa disponible. Las capacidades del F3 se vuelven a comprobar si carga esta versión. [Resultados del F3](turnip_poco_f3_20261116.md).

# Writing local: Windows y Android con Avalonia

La aplicación final de Windows con el curso completo se desarrolla y documenta en
[`../course_app`](../course_app/README.md). Esta carpeta conserva el prototipo
0.1.6 y su catálogo congelado; la aplicación final extiende ese catálogo sin cambiarlo.

Prototipo independiente de la aplicación Windows Forms. Comparte interfaz, catálogo, recomendaciones de capacidad, descargas verificadas, ejercicios nuevos, parser y sesiones JSON. Windows y Android ARM64 desde API 28 ejecutan el puente C en procesos hijos aislados, con calibración y reparto CPU/GPU compartidos. Los modelos se guardan fuera del paquete de aplicación y pueden cambiarse sin reinstalarla. [Entrega adaptativa 0.1.6](docs/adaptive_runtime_20261118.md).

La entrega Android **0.1.6** está en `artifacts/android-0.1.6/org.kevinlima.writinglab-Signed.apk`. Incluye el motor aislado y Mesa Turnip. Los GGUF se preparan por separado.

La entrega de Windows **0.1.6** está en `artifacts/windows-0.1.6/WritingApp.Desktop.exe`. Conserva la carpeta completa con sus DLL y `writing_worker.exe`; necesita .NET 11 Runtime para ejecutarse.

Ambas entregas usan llama.cpp **b12359**, que incorpora la arquitectura LFM3. LFM3-1.7B queda pendiente de incorporar al catálogo de la app. Sus pruebas de 40 casos se registran por separado. [Actualización del motor](docs/llama_cpp_turnip_20261113.md), [evaluación de LFM3](../documentation/lfm3_17b_phase1_20261117.md).

Windows y Android ARM64 ofrecen Vulkan y CPU. Android x86_64 usa CPU. El APK requiere Android 8/API 26 de 64 bits. Vulkan requiere API 28 y un controlador compatible con Vulkan 1.2 o posterior. Auto estima una distribución completa o parcial y compara CPU con GPU: tres muestras utilizables, calentamiento separado y razón CPU/Vulkan mínima de 1,15. En GPU con KGSL se conserva Turnip. Las demás usan el controlador del sistema. El perfil incluye modelo, prompt, parámetros, runtime, controlador y alimentación; se comprueba de nuevo el presupuesto al cargar. La primera carga puede tardar varios minutos y es cancelable. [Implementación y pruebas actuales](docs/adaptive_runtime_20261118.md); [validación móvil anterior](docs/android_measured_backend_20261117.md).

Para probar en un teléfono, copia el APK final al dispositivo e instálalo manualmente. Abre Writing Lab, revisa el modelo sugerido y pulsa Descargar / preparar; los pesos no están incluidos en el APK. Después pulsa Cargar modelo y usa un ejercicio o un ejemplo. La primera preparación necesita espacio para el GGUF además de la aplicación y conexión al proveedor. Si ya tienes el GGUF exacto, puedes importarlo mediante el selector de documentos. Para futuras pruebas conectadas se incluye `scripts/android_try_emulator.ps1`; ese script se dirige solo a un emulador, sin instalar en teléfonos por accidente.

## Flujo de uso

1. Revisa la sugerencia inicial basada en RAM disponible y almacenamiento. Puedes seleccionar cualquier otra entrada del catálogo y su cuantización. La sugerencia estima capacidad; no es una puntuación de calidad ni garantiza que el sistema permita la carga.
2. Pulsa **Descargar / reanudar**. El gestor de Android puede mantener la transferencia en segundo plano. Writing Lab verifica tamaño, cabecera GGUF y SHA-256 y guarda las descargas completas en sus archivos permanentes. Si Android aplaza esta operación, se recupera al abrir la aplicación o al cargar el modelo. Puedes usar el botón de descarga para volver a ver el progreso. **Cancelar transferencia** retira el trabajo activo del gestor. Windows reanuda su archivo parcial mediante HTTP Range. **Importar GGUF…** permite usar un archivo exacto ya descargado.
3. Selecciona **Auto Vulkan/CPU**, **Vulkan** o **CPU** y pulsa **Cargar modelo**. En Windows y Android ARM64/API 28+, Auto mide y guarda el backend y las capas en la primera carga. Vulkan manual utiliza una distribución estimada y recuperación de carga acotada; no compara velocidad ni cambia a CPU silenciosamente. CPU carga directamente. La interfaz muestra GPU y capas efectivas. Un fallo técnico durante la evaluación libera el worker e invalida su perfil; la respuesta no se reintenta automáticamente. Solo se carga un modelo a la vez.
4. Elige un ejercicio A1/A2, usa un ejemplo o escribe una respuesta. **Evaluar** muestra el juicio del modelo, texto corregido, retroalimentación y estado del JSON. Una marca de correcto es una afirmación del modelo, no un gold oculto.
5. **Intentos de formato** vale 1 inicialmente; puedes elegir 2 o 3. Solo se reintenta una salida inutilizable según el parser. Cada salida RAW, semilla y estado se conserva. Los errores técnicos y la cancelación no disparan reintentos.
6. **Exportar sesión JSON** usa el selector de archivos del sistema. También se guardan checkpoints locales después de cada respuesta recibida. Un cambio de entrada invalida el resultado visible anterior.

La descarga requiere red. Tras preparar los pesos, la inferencia funciona sin conexión. No se transmiten las respuestas a un servicio de inferencia externo. Las sesiones incluyen el texto introducido; los archivos locales permanecen bajo control del usuario.

## Catálogo y procedencia

El catálogo incorpora las **13 configuraciones** de la demo anterior: MiniCPM5 2B F16/Q8/Q4, Qwen3.5 4B Q8/Q4, Gemma 4 E2B QAT Q4/UD-Q4/UD-Q2, LFM2.5 1.2B BF16/Q8/Q4 y LFM2.5 2.6B Q8/Q4. Conserva sus identidades y hashes. LFM usa licencia `lfm1.0`; las licencias y fuentes están disponibles en los detalles del modelo.

Los Qwen experimentales se convirtieron localmente: **no tienen una URL inventada para esos bytes**. Se pueden reutilizar en este Windows o importar como GGUF exacto. Para que Qwen también tenga una opción descargable se añadieron **dos entradas separadas de Unsloth**, con revisión y hashes propios. No son los GGUF del benchmark y sus resultados anteriores no se les atribuyen. No se sustituye una entrada por otra silenciosamente.

`scripts/generate_portable_assets.py` genera recursos pequeños a partir del catálogo/manifiesto existente. Copia solo metadatos y prompts; no incluye casos ni gold de los benchmarks en la aplicación. Las dos variantes Qwen descargables están fijadas a `unsloth/Qwen3.5-4B-GGUF`, revisión `e87f176479d0855a907a41277aca2f8ee7a09523`, consultada mediante la API primaria de Hugging Face. El resto conserva las fuentes ya verificadas del proyecto.

Windows busca además el directorio `SLM_A1A2/models` si se ejecuta dentro del checkout; utiliza los archivos existentes sin copiarlos o descargarlos otra vez. Fuera del checkout usa `%LOCALAPPDATA%/WritingApp/Models`. Android usa el directorio privado de la aplicación, sin exigir acceso amplio al almacenamiento. Exportar o importar usa el selector de documentos.

## Capacidad, generación y reintentos

La estimación inicial suma `1,45 × bytes del GGUF + 384 MiB + 64 KiB × tokens de contexto`. El presupuesto es el menor entre el 75 % de RAM disponible y el 45 % de RAM total. Son márgenes iniciales de ingeniería, no mediciones por arquitectura; RAM compartida de GPU, KV, activaciones, driver y sistema pueden producir un uso distinto. Si no cabe ningún candidato preferido, se propone el menor y se advierte que no cumple la estimación. La elección manual permanece disponible.

La sugerencia inicial prioriza Gemma E2B si cabe en la estimación conservadora; después MiniCPM2B y LFM1.2. Qwen y todas las demás entradas conservan elección manual. Una vez disponibles los pesos, Auto calibra ese modelo y su reparto, sin un mínimo excluyente de 4 GiB ni descarte general de GPU integradas. Esta estimación inicial no certifica calidad ni rendimiento. El detalle de descarga muestra MB/s y tiempo estimado; proveedor, Wi-Fi y políticas del dispositivo siguen limitando la velocidad. El gestor del sistema necesita espacio temporal adicional durante su verificación/copia.

Android usa contexto 2048; Windows usa 4096. Se mantienen hasta 512 tokens de salida y los parámetros por familia. Las plantillas proceden del GGUF con thinking desactivado donde es controlable. Para Qwen/MiniCPM/Gemma se incorpora el prompt propuesto a partir de la revisión humana; para LFM se mantiene el base. Las configuraciones de los dos finalistas se evaluaron posteriormente en [200 casos](../documentation/finalists_200_results_20261117.md); la calibración técnica no añade puntuaciones de calidad.

La demo 0.1.2 utiliza `writing_json_grammar_v1` en llama.cpp para guiar el contrato JSON. Si la plantilla termina prefijando literalmente `<think>` e ignora el flag, se cierra ese prefijo en la entrada antes de generar. No se recorta ni repara el RAW devuelto. Se registran formato, cierre de prefijo, tokens y tiempos; la gramática no garantiza un juicio lingüístico correcto ni un objeto completo si se agota el límite. El harness admite `--unconstrained` para separar esa política de producto de una generación libre. Las sesiones nuevas usan esquema `writing_cross_demo/1.1`; los resultados históricos no se recalculan.

Los reintentos mantienen ejercicio, respuesta y prompt, y usan semillas **42, 43 y 44**, registradas por tentativa. Cambiar la semilla evita que una repetición determinista sea necesariamente idéntica; no garantiza corregir el formato. `STRICT` y `RECOVERED` se consideran utilizables, conservando la distinción. `INVALID_JSON`, `INVALID_SCHEMA` e `INCONSISTENT` permiten otro intento si fue solicitado. El parser no evalúa la veracidad lingüística para decidir un reintento.

Las sesiones tienen propósito `INTERACTIVE_DEMO_NOT_BENCHMARK`. Los checkpoints son acumulativos y tienen nombres únicos; no deben sumarse como evaluaciones independientes. Si se cancela o falla una tentativa posterior, los checkpoints ya guardados conservan las respuestas anteriores.

## Estructura y NativeAOT

- `WritingApp.Shared`: contratos, recursos portables, almacenamiento, estimación, reintentos y exportación.
- `WritingApp.Native`: transporte UTF-8 con worker aislado y adaptador P/Invoke estático para la ruta heredada; ABI C versionado.
- `native`: puente C y recetas de compilación contra llama.cpp b12359, commit `b1b770d90d94cad9e9ea5b993bdbc383a522fb28`.
- `WritingApp.UI`: vista compartida responsive y bindings compilados de Avalonia.
- `WritingApp.Desktop` / `WritingApp.Android`: arranque, perfiles de dispositivo y almacenamiento de cada plataforma.
- `WritingApp.Tests`: fixtures sintéticas; no cargan modelos.
- `WritingApp.Smoke`: prueba técnica explícita con un modelo existente; nunca descarga pesos ni accede al benchmark.

Se fija **.NET SDK 11.0.100-rc.3.26522.148** en este subproyecto, sin modificar el SDK estable de la demo WinForms. Avalonia se fija a **12.1.5**. Los recursos son embebidos, la serialización usa `System.Text.Json` source generation con reflexión desactivada, los proyectos compartidos activan analizadores AOT y no hay contenedor DI basado en reflexión. Esto prepara una evolución hacia NativeAOT; no equivale a haber validado una publicación NativeAOT en todas las plataformas. La guía [Native AOT de Avalonia](https://docs.avaloniaui.net/docs/deployment/native-aot) describe las condiciones adicionales.

## Compilar

Desde este directorio:

```powershell
dotnet run --project WritingApp.Tests/WritingApp.Tests.csproj -c Release
dotnet build WritingApp.Desktop/WritingApp.Desktop.csproj -c Release
dotnet publish WritingApp.Desktop/WritingApp.Desktop.csproj -c Release -r win-x64 --self-contained false -o artifacts/windows
```

Antes de usar inferencia, prepara las dependencias b12359 y ejecuta `scripts/build_adaptive_runtime.ps1 -Platform All`. La variante nueva queda en `native/artifacts/b12359-adaptive-v1/`; conserva intacta la anterior. MSBuild copia DLL y worker al lado del ejecutable. `scripts/windows_build.ps1` valida dependencias y publica en DesktopRelease. `-Open` abre la aplicación. [Instrucciones nativas](WritingApp.Native/README.md).

Android requiere las bibliotecas por ABI dentro del APK, además del SDK, JDK y NDK adecuados. `scripts/android_build.ps1` selecciona SDK/JDK solo para ese proceso y exige las bibliotecas CPU. El paquete de esta entrega incluye también el plugin Vulkan ARM64. La carga .NET Android se preparó de manera aislada y usa bindings preview6 y runtime RC3 con CoreCLR/JIT. [Inventario Android](android_environment.json).

```powershell
# Prueba nueva, sintética, fuera de los benchmarks, con pesos ya existentes:
dotnet run --project WritingApp.Smoke/WritingApp.Smoke.csproj -c Release -- --execute --backend AutoVulkanCpu --model 09-lfm25-12b-q4-k-m --context 2048
```

El harness exige `--execute`; `--load-only` omite el chat y solo comprueba la carga. Los scripts no configuran un remoto Git ni publican datos. Los binarios, modelos, SDK/NDK locales, paquetes y logs quedan fuera de Git; la procedencia y verificaciones se documentan por separado.

## Evaluaciones y límites

La comparación de 200 preguntas de Gemma y Qwen en CPU/Vulkan ya se ejecutó y está documentada por separado. Esta entrega no repitió ese benchmark ni usó sus respuestas para ajustar prompts. Las muestras sintéticas de calibración verifican compatibilidad y tiempo local; no validan precisión lingüística ni deben sumarse a 40/120/200.

Con reintentos deben informarse al menos dos resultados: **éxito al primer intento** y **éxito tras recuperación hasta el límite**, además del número de generaciones, latencia y consumo. Elegir la primera salida que cumple el contrato es una regla de producto distinta de elegir la respuesta lingüísticamente mejor. Las métricas históricas de una tentativa permanecen separadas.

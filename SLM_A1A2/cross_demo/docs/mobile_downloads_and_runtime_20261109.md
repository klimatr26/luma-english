# Versión 0.1.2: descargas móviles, CPU ARM y salida JSON

Trabajo del 9 de noviembre de 2026, America/Guayaquil. Continúa la corrección Android0.1.1 del commit `62c7e60`. Se trabajó sin subagentes. Esta actualización corresponde al prototipo interactivo, no a los benchmarks experimentales.

## Problemas observados

El usuario comunicó interrupciones de descarga al apagar la pantalla en un **POCO F8 Pro con Android16** y adjuntó una captura con `Android.OS.NetworkOnMainThreadException`. También señaló latencia muy alta en modelos mayores de2B en el teléfono conectado y salidas no JSON de LFM2.5-2.6B.

La versión anterior ejecutaba la transferencia desde una tarea ligada a la vista y conservaba el contexto de sincronización de UI en sus continuaciones. Ciertos streams HTTP Android pueden realizar trabajo síncrono antes de devolver una tarea: usar `await` no bastaba para excluir toda operación de red del hilo principal. Además, una interrupción eliminaba el parcial y no había un trabajo de descarga del sistema que pudiera sobrevivir al proceso.

El F8 Pro no estaba conectado por ADB. Las pruebas físicas de esta actualización se hicieron en el dispositivo conectado **M2012K11AG/alioth, Android13/API33, ARM64, Adreno650**, cuyo driver Vulkan1.1.128 obliga a CPU con el backend fijado. No se atribuye a Android16 una validación física que no se realizó.

## Descarga y recuperación

Android utiliza ahora `DownloadManager` mediante `AndroidDownloadTransport`: es el servicio del sistema diseñado para transferencias HTTP largas, cambios de conectividad y recuperación fuera de la vida de una actividad. Véase la [referencia oficial de Android](https://developer.android.com/reference/android/app/DownloadManager). No se añadió un servicio propio que dependa de mantener abierta la pantalla ni se solicitó excluir la app de las políticas de batería.

`BackgroundModelDownloads` guarda un ticket pequeño con ID del trabajo y la identidad/tamaño/SHA del modelo. Al reabrir la app, la selección puede recuperar el modelo pendiente y el mismo botón **Descargar / reanudar** vuelve a consultar ese trabajo. Una cancelación del seguimiento de UI no cancela la descarga del sistema. El botón Cancelar transferencia sí solicita explícitamente retirar ese trabajo y su temporal. Si el proceso termina justo después de publicar el modelo privado, la siguiente solicitud verifica el modelo y retira el trabajo redundante que pudiera quedar.

El temporal se guarda en almacenamiento externo **privado de la app**, no en un archivo arbitrario de Downloads. Al completar, se importa a la caché interna y se verifican tamaño, cabecera GGUF y SHA completo. No se considera modelo una descarga parcial. Durante esa copia/verificación se necesita espacio para ambas copias. Las fuentes siguen fijadas a las mismas revisiones y hashes; no se aceptan licencias o accesos del proveedor automáticamente. Se conservan las alternativas de importación manual y las identidades separadas de Qwen experimental/Unsloth.

Para el downloader administrado usado en Windows se añadieron `SocketsHttpHandler`, entrada completa en un worker y parciales propios reanudables mediante HTTP Range. Un206 solo se acepta si el rango coincide con el offset y tamaño esperados; si el servidor ignora Range y responde200, se reinicia ese parcial en vez de anexar una respuesta completa. Se verifica de nuevo todo el archivo antes de publicarlo. Un EOF técnico conserva el prefijo para la siguiente solicitud explícita. No se añade reintento propio ante429; en Android las decisiones de reintento pertenecen al servicio del sistema y se muestran como su estado.

La importación y lectura de streams también entran en un worker. La UI muestra MB/s y una estimación de tiempo, separando transferencia de copia/verificación. Reanudar evita repetir bytes; sacar la red del hilo de UI y usar el servicio del sistema elimina el error mostrado. Esto no garantiza superar límites de Wi-Fi, proveedor, conexión móvil o políticas del fabricante. No se instaló un gestor externo ni se cambiaron ajustes de seguridad.

### Comprobación física de descarga

Se creó un paquete de validación **separado**, `org.kevinlima.writinglab.downloadprobe`, que enlaza el mismo transporte y coordinador de producción. Usa como máximo un GGUF LFM1.2 Q4 público de730895168 bytes por trabajo; no realiza inferencia ni usa la caché de Writing Lab. El usuario aceptó su instalación. Al principio, la configuración de validación omitió el assembly store por FastDev: CoreCLR no pudo cargar `System.Private.CoreLib`. Se corrigió el empaquetado de esa sonda con ensamblados embebidos; ese fallo no era del APK de producción.

| Trabajo de validación | Resultado observado |
|---|---|
|2771|El monitor se separó tras2s; el proceso propietario25455 fue reemplazado por26157; al consultar después, el mismo trabajo estaba completo con730895168 bytes. Se retiró mediante el servicio. No se conoce su instante exacto de finalización.|
|2772|Se inició con pantalla apagada; ambos snapshots de PowerManager indicaron `mWakefulness=Dozing`. Tras separar el monitor y terminar el proceso propietario, el mismo ID pasó de69594 bytes a66223446 bytes entre21:58:31.944 y21:58:44.712, con un proceso nuevo26541.|
|Limpieza2772|Se canceló explícitamente; el último contador observado fue94688252 bytes. Se retiró su temporal y se desinstaló el paquete de validación.|

En el intervalo medido del segundo trabajo avanzaron66153852 bytes en12,768s: aproximadamente **5,18MB/s decimales**. Es una observación de esa conexión/dispositivo, no una velocidad garantizada. PowerManager Dozing no acredita una prueba prolongada de Doze profundo. Falta repetir en el F8 Pro/Android16 y con sus políticas OEM.

Una comprobación acotada desde Windows solicitó32MiB en rangos del mismo archivo: una transferencia de16MiB tardó1,92s; dos rangos simultáneos de8MiB tardaron1,61s en conjunto. El orden y la caché no estaban controlados, y no es Android. No justifica prometer multiplicaciones de velocidad ni añadir múltiples descargas del mismo archivo en Android; se priorizó la recuperación y el servicio del sistema.

## Rendimiento CPU y recomendación móvil

Los flags efectivos ya contenían `-O3`; el problema no era una compilación sin optimizar. Sin embargo, solo se distribuía un backend CPU ARM de compatibilidad general. Ahora se compilan las siete variantes `android_armv*` que proporciona el commit fijado de llama.cpp. Cada módulo ofrece `ggml_backend_score`, compilado por upstream sin los flags ISA/LTO del kernel: se consulta esa puntuación de compatibilidad y se carga la más alta. No se ejecuta un kernel incompatible para averiguar si funciona. Se conserva un fallback armv8.0 bajo `libggml-cpu.so`.

En el teléfono conectado se seleccionó **android_armv8.2_2**, con DOTPROD y aritmética vectorial FP16. Los dispositivos sin esas instrucciones conservan una variante compatible. El nombre efectivo queda registrado en `EngineState.Device`. La elección no utiliza la calidad de una respuesta.

Se realizaron dos generaciones sintéticas por CLI nativa, una por implementación CPU. Se usó el mismo LFM1.2 Q4 verificado, contexto2048, semilla42, máximo512, prompt y respuesta de demostración nuevos; se comprobó el SHA de la copia temporal. La primera ejecución forzó el backend base con `WRITINGLAB_CPU_BASELINE=1` y la segunda usó la selección normal. No se cambiaron afinidad, reloj ni políticas de energía; no hubo control térmico y el orden no fue aleatorio.

| Implementación | Prompt | Salida | Tiempo total | Procesamiento del prompt | Decodificación |
|---|---:|---:|---:|---:|---:|
|Base armv8.0|301 tokens|48 tokens|11,660s|9,189s|2,442s|
|android_armv8.2_2|301 tokens|48 tokens|4,752s|2,686s|2,038s|

Los RAW resultaron idénticos. El tiempo total observado fue aproximadamente2,45 veces menor; la mejora se concentró en el prompt y fue bastante menor en decodificación. Dos muestras no establecen rendimiento sostenido ni un factor universal para4B. Ambos resultados fueron **INCONSISTENT** según el parser real de la app: `is_correct=true` mientras se cambiaba `wakes` por `wake`. La mejora técnica no se presenta como mejora de precisión.

La sugerencia Android ahora prioriza LFM1.2 Q4 y después MiniCPM2B Q4; una RAM amplia no selecciona automáticamente un modelo mayor de2B. Todos siguen disponibles mediante elección manual. La estimación de capacidad continúa siendo una heurística, distinta de calidad y latencia. En este teléfono, los modelos grandes siguen usando CPU; no hay promesa de fluidez para Qwen4B.

## LFM2.6 y contrato JSON

Se inspeccionó la plantilla del GGUF exacto ya descargado. Su final agrega literalmente `<|im_start|>assistant\n<think>` al pedir generación; no consulta `enable_thinking`. Una salida técnica anterior conservada consumió el límite de512 tokens en razonamiento y dejó incompleto el objeto JSON. No se interpreta que el flag false haya desactivado una función que esa plantilla no atiende.

La política **de producto** 0.1.2 conserva el flag false para las plantillas que lo admiten y, si queda un `<think>` prefijado al final, lo cierra explícitamente en la entrada antes de decodificar. No se modifica el GGUF ni se recorta el RAW. Además, `writing_json_grammar_v1` guía el objeto y los tipos requeridos por el parser. El sampler común de upstream valida primero el token muestreado y solo aplica la gramática a todo el vocabulario si debe rechazarlo y remuestrear, evitando el coste de hacerlo siempre.

Una primera implementación aplicaba la gramática al vocabulario completo en cada token; su RAW/log se conservan como ensayo de desarrollo, no como runtime congelado ni benchmark. Tras revisar ese coste se sustituyó por el camino común de upstream manteniendo sampling explícito. El ensayo final Windows/Vulkan con LFM2.6 Q4 produjo **STRICT**,197 tokens de salida, cierre de prefijo registrado y1,688s totales (0,367s de prompt y1,096s de decodificación). No se ejecutó una nueva comparación completa de calidad.

Ese objeto todavía incluyó una entrada de «no error» en su lista; un JSON estructuralmente válido **no garantiza una evaluación lingüística acertada**. La gramática tampoco asegura completar el objeto si se agota el límite. La app conserva las advertencias de consistencia, los intentos opcionales hasta3, el RAW y las semillas; no selecciona por calidad ni transforma una salida incorrecta en correcta.

El ABI nativo pasa a **2** y rechaza mezclarlo con los assemblies/bibliotecas anteriores. Se exportan métricas de tokens, tiempo de prompt y decodificación. Las sesiones nuevas usan `writing_cross_demo/1.1` y registran formato de salida y cierre de prefijo. `--unconstrained` del harness permite generar sin esa política. El SHA del sistema sigue representando el mensaje de sistema, no todo el prompt renderizado; los cambios de formato se trazan por versión, código/gramática, GGUF y métricas.

Los resultados de40/120 casos, sus prompts congelados y sus puntuaciones no se recalculan ni se atribuyen al modo guiado. Para un estudio posterior se deberá fijar y declarar esta política como parte del sistema evaluado antes de usar datos independientes. No se creó ni consultó el test final.

## Entrega y verificación

- APK actual: `artifacts/android-0.1.2/org.kevinlima.writinglab-Signed.apk`, versión0.1.2/código3, firmado para desarrollo. Conserva el mínimo CPU/API26 y el plugin Vulkan ARM64/API28. No cambia el requisito Vulkan1.2 de GPU de la versión anterior.
- Windows: `artifacts/windows-0.1.2/`, con sus DLL completas y .NET11 Desktop Runtime instalado. La publicación anterior se conserva.
- [Índice de hashes, versiones y evidencias](../manifests/mobile_update_verification_20261109.json). Binarios, SDK, modelos y RAW/logs permanecen locales fuera de Git; el repositorio conserva fuentes, documentación y hashes.
- Pruebas finales: **24/24** de servicios, **4/4** de UI/exportación, **6/6** del prefijo de pensamiento y3 rutas de rechazo/aislamiento del ABI2 en el teléfono. También se verificaron las22 bibliotecas SO del APK contra staging y se comprobaron firma/alineación.
- Se verificaron nuevamente24 artefactos Fase1. Se conservaron las fuentes y derivados de evaluación v2 y los blobs originales; el índice registra la comprobación final. No se usaron subagentes ni se configuró remoto.

La validación controlada de esta tarea inició **cuatro generaciones nuevas de demostración**: dos con LFM2.6 en Windows durante la implementación del sampler, y dos con LFM1.2 en el teléfono para comparar CPU. Ninguna fue parte de un benchmark. Las sondas de descarga, política y rechazo no generaron texto. Los resultados permanecen separados de los nueve ensayos técnicos anteriores del prototipo; las pruebas independientes que haga el usuario en la aplicación no se cuentan en este registro.

Para reproducir se conservan los scripts de publicación, las fixtures de `WritingApp.Tests`, las herramientas nativas `inference_smoke.cpp`, `prompt_policy_smoke.cpp`, `backend_rejection_probe.cpp` y el host separado `WritingApp.Android.DownloadProbe`. El host de descargas es solo una herramienta de validación: no se incluye en la app entregada. Su configuración exige ensamblados embebidos y no FastDev. Los temporales propios de pruebas, incluida la copia GGUF bajo `/data/local/tmp/writinglab-v012-smoke`, se retiraron tras comprobar sus nombres; no se borró la caché de modelos de Writing Lab.

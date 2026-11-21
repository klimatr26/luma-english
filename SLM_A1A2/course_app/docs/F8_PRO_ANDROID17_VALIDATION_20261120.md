# Luma English · POCO F8 Pro con Android 17

Fecha: 20 de noviembre de 2026, America/Guayaquil. Pruebas locales de integración
y rendimiento; no son una nueva evaluación de precisión del benchmark.

## Resultado

La aplicación funciona en el POCO F8 Pro actualizado a Android 17/API 37,
HyperOS `OS4.0.6.0.XPKMIXM`. Vulkan funciona mediante Mesa Turnip y no produjo el
error de pipelines observado en versiones anteriores. La elección del backend
depende del modelo y de las medidas:

| Modelo Q4, contexto 2048 | CPU, mediana de 3 | Vulkan, mediana de 3 | Capas GPU probadas | Elección Auto |
|---|---:|---:|---:|---|
| Gemma E2B UD-Q4_K_XL | 10,961 s | 11,335 s | 36/36 | CPU |
| Qwen 3.5 4B Unsloth Q4_K_M | 35,979 s | 25,680 s | 33/33 | Vulkan |

Para Qwen, la razón CPU/Vulkan fue **1,401**, una reducción de latencia del
**28,62 %** en esta consigna. En Gemma, Vulkan tardó aproximadamente un 3,4 % más.
La política existente exige tres respuestas utilizables y una razón mínima de
1,15; no se cambió para obtener estos resultados. Esto demuestra por qué la
presencia de una GPU reciente no basta para seleccionar Vulkan en todos los
modelos.

Los tokens de salida fueron 237 CPU/230 Vulkan en Gemma y 167 CPU/155 Vulkan en
Qwen. Aunque las consignas, semilla y sampling son iguales, las respuestas de
ambos backends no son idénticas. Los cocientes describen la latencia completa de
esta tarea, no una aceleración de kernels aislada ni un resultado universal.

## Equipo y configuración

- POCO F8 Pro, modelo `2510DPC44G`, arquitectura ARM64; Adreno 830.
- Firmware: `POCO/annibale_global/annibale:17/CP2A.260605.016/OS4.0.6.0.XPKMIXM:user/release-keys`.
- RAM reportada por Android: 11.661.799.424 bytes; la memoria disponible cambió
  durante las pruebas. No se forzó presión de memoria ni un límite artificial.
- Página del sistema: 4096 bytes. El APK conserva además alineación para 16 KiB.
- El comando de Android 17 `am memory-limiter status` informó **disabled** antes
  y después. Es una observación de este firmware: el agente no lo desactivó.
- Ahorro de batería desactivado al consultar; alimentación USB durante las
  mediciones. No se modificaron ajustes globales de energía o seguridad.
- Temperatura de batería observada desde 26,6 °C al inicio hasta 41,5 °C tras
  carga sostenida. No se hizo un ensayo energético o de autonomía.
- .NET 11 GA/Avalonia 12.1.5 y los binarios existentes `b12359-adaptive-v1`, con
  Turnip 26.2.7/loader 1.4.368. No se modificó llama.cpp ni el puente C++.
- Contexto 2048, semilla 42, máximo 512 tokens, un intento en los ejemplos del
  curso, thinking desactivado cuando el modelo lo permite y gramática JSON de
  producción. No se ajustaron prompts o parámetros según las respuestas.

Los pesos se reutilizaron del teléfono y se comprobaron por tamaño y SHA-256
antes de preparar los dos modelos:

| Identidad del catálogo | SHA-256 |
|---|---|
| `13-gemma4-e2b-ud-q4-k-xl` | `e531007218dfab990486a5de7676a6932d6ea8dea233d1f698d7c21cf8a16889` |
| `portable-unsloth-qwen35-4b-q4-k-m` | `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` |

No se atribuyen a estas variantes las puntuaciones de otros GGUF. El informe
anterior del prototipo en Android 16 sigue en
[android_measured_backend_20261117.md](../../cross_demo/docs/android_measured_backend_20261117.md).
Las diferencias con él no permiten atribuir cambios de velocidad solamente a
Android 17: cambiaron firmware, implementación de selección, estado térmico y
condiciones de ejecución.

## Actualización y conservación de datos

El teléfono tenía Writing Lab 0.1.5, código 6. Se conservó una copia local del APK
instalado y se comprobó su certificado antes de actualizar: es el mismo usado por
Luma English. No se desinstaló ni se ejecutó `pm clear`.

Se localizaron seis GGUF: Gemma, Qwen, MiniCPM, LFM2.5 2.6B Q4 y LFM2.5 1.2B
Q4/Q8. No se borraron ni reemplazaron. Las tres sesiones anteriores y el
directorio de perfiles del prototipo se respaldaron antes de las pruebas; el
archivo TAR obtenido después resultó **byte idéntico** al anterior.

El arnés usa `files/phone-verification/<run>/course-test.db`. Las 30 actividades
de prueba, las respuestas del modelo, los borradores y las restauraciones no se
escriben en la base personal. Una copia de solo lectura de esta última confirmó
cero intentos cerrados, cero sesiones Writing, cero intentos RAW y cero borradores.
El APK normal muestra el curso personal en 0/33, como corresponde.

Al terminar se restauró **Luma English 1.1.0, código 100100**, APK normal ARM64,
SHA-256 `2d2cf85862763fd6e1d1ddbb5c07b11e1e03d9b9b837ef72d55d35658a24b325`.
El paquete no permite `run-as` porque no es depurable y excluye las actividades
de diagnóstico. ADB informó arranque correcto; el usuario confirmó que veía el
curso y se guardó una captura de la aplicación en primer plano.

## Método y comprobaciones

`PhoneVerificationActivity`, compilada solo con `CourseAutomation=true`, instala
la misma vista y VM del curso sobre la base de pruebas separada. El controlador
`verify_android_phone.py` exige un serial físico explícito, nunca desinstala ni
borra datos y retiene cada informe bajo un identificador de ejecución distinto.

Las pruebas principales de interfaz pasaron **43/43**: tres lecciones, las 30
claves de ejercicios cerrados, borrador, teclado Android, introducción/borrado a
través de los eventos del TextBox, giro horizontal/vertical, advertencia de JSON
incompleto, respuesta cerrada incorrecta, exportación JSON/CSV, respaldo y
restauración, y selección avanzada Qwen 2B sin descargarlo.

HyperOS rechazó la inyección de eventos externos por ADB con `INJECT_EVENTS`.
No se cambió esa protección. La automatización actuó sobre los controles reales
desde la propia aplicación de pruebas; el usuario colaboró al desbloquear,
apagar la pantalla y confirmar el APK normal. No se presenta como automatización
de todos los gestos físicos por ADB.

La comparación del motor usa la política compartida: carga, un calentamiento
excluido de la mediana y tres muestras por ruta completada. Los ejemplos son
sintéticos y ajenos al benchmark; la compilación de pipelines y la carga no se
incluyen en los tiempos de inferencia de la tabla. La preparación completa,
incluidas verificación y calibración, tardó aproximadamente 102,9 s para Gemma y
251,9 s para Qwen.

Después de elegir backend se evaluaron los dos ejemplos originales de Writing
de la primera unidad. En los cuatro ejemplos principales se obtuvo `STRICT`,
con el veredicto esperado y una respuesta utilizable:

| Modelo/backend elegido | Ejemplo correcto | Ejemplo incorrecto |
|---|---:|---:|
| Gemma/CPU | 8,404 s | 10,589 s |
| Qwen/Vulkan | 17,773 s | 27,232 s |

Se inspeccionó el contenido generado además del parser: ambos conservaron el
ejemplo correcto y detectaron el error introducido en el otro. Es una comprobación
de demostración, con entradas muy pequeñas; no equivale a precisión del 100 %
ni a revisión docente del conjunto experimental.

## Memoria

Se muestrearon los procesos de la aplicación y del worker nativo, aproximadamente
cada tres segundos, mediante el UID propio y `/proc`. Las transiciones previas
a descargar el backend anterior se excluyeron para no contar un modelo CPU aún
cargado como memoria del siguiente backend Vulkan.

| Modelo/ruta | Máximo PSS observado app + worker | Máximo RSS observado app + worker |
|---|---:|---:|
| Gemma/CPU | 4077 MiB | 4194 MiB |
| Gemma/Vulkan | 1755 MiB | 1870 MiB |
| Qwen/CPU | 4762 MiB | 4886 MiB |
| Qwen/Vulkan | 816 MiB | 920 MiB |

**Estos valores no son el total de RAM más memoria GPU.** Los contadores KGSL
no fueron accesibles y no se dispone de un pico fiable de VRAM/allocaciones GPU
atribuible al modelo. La GPU comparte memoria del dispositivo; una caída del
PSS visible en CPU no prueba una reducción igual del consumo físico total.
Tampoco se sumaron máximos de procesos de instantes diferentes: se sumaron las
muestras simultáneas y después se tomó su máximo.

Son máximos observados por sondeo, no capturas garantizadas de todos los picos
transitorios. Gemma se midió en una fase técnica posterior con selección manual
de CPU/Vulkan; esa fase no reemplaza sus medianas en primer plano. Las primeras
filas del controlador carecían de UTC individual: el resumen usa la hora de
creación del archivo original en Windows y el tiempo monotónico transcurrido,
con incertidumbre alrededor de los cambios de fase. Los RAW y muestras se
conservan localmente.

## Caché, pantalla apagada y descargas

Se comprobó que una segunda preparación con el mismo APK conservó exactamente
la clave y fecha del perfil y no emitió pasos `Calibrando`: preparación 9,870 s,
incluidos hash y carga. Actualizar el APK puede cambiar la huella de bibliotecas
nativas del paquete y provocar una nueva calibración. Es una invalidación
conservadora; la primera preparación del APK normal puede medir de nuevo.

Se hicieron dos transferencias técnicas separadas usando el transporte real de
DownloadManager y una URL fijada de LFM1.2 con identificador de prueba único:

- Trabajo 602: se recuperó como el mismo trabajo completo de 730.895.168 bytes
  tras apagar la pantalla y reiniciar el proceso de la app. La primera observación
  con pantalla apagada ya lo encontró completo, por lo que no se usa para afirmar
  en qué instante exacto terminó respecto del apagado.
- Trabajo 603: se inició con la pantalla ya apagada, se detuvo el proceso de la
  aplicación y después se recuperó el mismo ID, todavía `Running`, con
  **117.392.328 bytes recibidos**. Demuestra avance del trabajo del sistema sin
  depender del proceso de interfaz activo.

Solo se retiraron esos trabajos y archivos temporales. La carpeta de transferencias
quedó vacía; no se publicaron copias adicionales en el almacén de modelos ni se
tocaron descargas ajenas. Los pesos para inferencia se reutilizaron localmente;
las transferencias de prueba sí consumieron red. Los ensayos se hicieron con
alimentación USB, no durante Doze prolongado con el teléfono desconectado.

## Incidencias y trazabilidad

- La primera prueba de giro agotó su plazo con el teléfono bloqueado. Se repitió
  desbloqueado y pasó. La primera comparación Gemma también tuvo parte de su
  ejecución con pantalla apagada: se conserva como incidencia y no se usa como
  comparación principal en primer plano.
- La variante de diagnóstico retuvo una referencia de actividad durante cada
  prueba y una bandera de ventana para mantener la pantalla activa; no cambió
  ajustes globales. El APK normal restaurado no incorpora esa bandera de pruebas.
- La primera rutina de memoria esperaba reutilizar un perfil anterior incluso
  después de actualizar el APK y falló su aserción de caché. Se conservó el informe
  fallido. La huella de runtime había cambiado; se corrigió el arnés para comparar
  dos preparaciones dentro de la misma instalación y la corrección compiló.
  La reutilización física aquí reportada se verificó en una ejecución separada,
  con clave/fecha idénticas y cero
  pasos de calibración.
- El primer muestreador buscó hijos solo en `/proc/<pid>/task/<pid>/children`,
  que no mostró los workers en este dispositivo. Se cambió a enumeración del
  UID propio. La memoria de Gemma se recogió de nuevo en la fase técnica posterior;
  Qwen sí dispone del muestreo conjunto durante su comparación principal.
- Hubo **42 generaciones técnicas** en total: 20 de las dos comparaciones
  principales y sus ejemplos; el resto corresponde a la pasada con bloqueo,
  validación de memoria, invalidación tras actualizar y comprobación de caché.
  Todas son ejemplos sintéticos/del curso. Se conservaron las salidas de intentos
  no aceptados; no se ajustó el modelo para que pasara una prueba.

Las regresiones de software pasaron 29/29, 15/15 y 40/40. La verificación de los
dos APK normales pasó, incluida la ausencia del arnés de teléfono. No se alteraron
llama.cpp, los pesos ni los prompts congelados. Las pruebas de 40/120/200 no se
ejecutaron ni se recalificaron.

El [resumen legible por máquina](evidence/f8-android17-20261120/summary.json)
incluye modelo, hash, parámetros, muestras, selección y límites de memoria. Los
informes y capturas seleccionados se guardan en esa carpeta; los respaldos privados
de sesiones anteriores, APK, bases SQLite y logs extensos quedan fuera de Git.

## Interpretación y siguiente dispositivo

Gemma es la alternativa más rápida de las dos en estos ejemplos y mantiene su
papel como opción móvil inicial cuando cabe en memoria. Qwen sigue siendo una
opción avanzada viable con aceleración medida; sus resultados experimentales de
precisión anteriores se interpretan por separado de estas pruebas técnicas.

El siguiente dispositivo es el **POCO F3**: repetir el recorrido esencial,
comprobar Gemma/MiniCPM y medir su elección CPU/Vulkan. El resultado del F8 no se
convierte en una lista de modelos o backends permitidos por teléfono; la aplicación
sigue usando capacidades y medidas.

Para reproducir las fases de teléfono se compila el APK ARM64 con `-Automation`
y se usa `scripts/verify_android_phone.py` con serial y `--run` explícitos.
`--fresh` archiva perfiles anteriores sin borrar trazas. El resumen se genera con
`scripts/summarize_android_phone.py --directory artifacts/phone-f8-20261120`.
Al terminar debe restaurarse el APK normal con la misma firma y sin desinstalar.

# Luma English · inglés a tu ritmo

Aplicación para Windows y Android del proyecto de titulación. Integra tres unidades con
lecciones, 15 preguntas de opción única, 15 de una palabra y tres actividades de
Writing. La interfaz Avalonia 12.1.5 y la lógica .NET 11 GA se comparten con la
entrega Android. Los datos del curso y los modelos se conservan al cambiar el nombre.

El [informe de implementación y validación](docs/WINDOWS_IMPLEMENTATION_20261119.md)
incluye pruebas, capturas reales, tiempos, memoria, procedencia y límites observados.
La actualización 1.1.1 corrige la distribución del resumen de progreso en pantallas
estrechas; las [pruebas y capturas de la corrección](docs/HOME_SUMMARY_LAYOUT_20261120.md)
documentan el cambio.
La [validación en el POCO F3](docs/F3_ANDROID13_VALIDATION_20261120.md) documenta
el curso, los ejemplos de Gemma/MiniCPM en CPU, los fallos Vulkan, la descarga
con pantalla apagada y los ajustes pendientes de la selección automática.
La [actualización 1.1.2](docs/RUNTIME_MEMORY_TUNING_20261121.md) aplica plazos
adaptativos, caché de fallos, protección de primer plano y una propuesta de modelo
con reservas separadas de memoria total y memoria disponible.

## Usar en Windows

Abre **LumaEnglish.exe** dentro de `artifacts/windows-1.1.2/`. Conserva la carpeta
completa: incluye .NET y los archivos nativos. También se genera
`artifacts/LumaEnglish-Windows-x64-1.1.2.zip`, que puedes copiar y descomprimir en
otro Windows x64. No necesitas instalar .NET. Los pesos se preparan por separado.

1. Explora una unidad y su lección. Puedes empezar por cualquiera.
2. En **Practicar**, comprueba una opción o una palabra y lee su explicación.
3. Al llegar al Writing, escribe tu respuesta y prepara el modelo propuesto.
   La acción informa el tamaño cuando hace falta descargarlo. Puedes cancelar la
   preparación, que verifica el GGUF y compara CPU con Vulkan la primera vez.
4. Pulsa **Evaluar mi Writing**. Revisa el texto, los cambios y el comentario del
   modelo. **Ver JSON y detalles** muestra lo que produjo y permite exportarlo.
5. Revisa tus intentos desde **Mi historial**. En **Modelos y ajustes** puedes
   cambiar el modelo, exportar el progreso y restaurar un respaldo.

El curso funciona sin Internet. Después de preparar el modelo, también funciona
la evaluación sin conexión. Las respuestas no se envían a un proveedor de IA.
La marca de correcto expresa el juicio del modelo; no certifica la exactitud de
la respuesta. Un fallo de formato o un fallo técnico se presenta como advertencia.

## Usar en Android

Instala `artifacts/LumaEnglish-Android-android-arm64-1.1.2.apk` en un teléfono
ARM64 con Android 8 o posterior. Es una distribución directa para este proyecto,
firmada con la misma clave local de desarrollo que Writing Lab 0.1.6; no es un
paquete de tienda. Actualiza la aplicación existente, sin desinstalarla.
Conserva el identificador `org.kevinlima.writinglab`, sus modelos permanentes y
sesiones anteriores. El curso tiene su propia base SQLite.

La navegación inferior, las lecciones y el Writing se adaptan al ancho y a la
orientación; las zonas de las barras del sistema quedan libres. Puedes importar
un GGUF exacto mediante el selector de documentos o dejar la descarga al gestor
del sistema Android. Las descargas sobreviven al cierre de la interfaz; cancelar
su seguimiento no borra un modelo completo.

Android propone inicialmente Gemma si hay memoria suficiente, después MiniCPM
y LFM 1.2B. Las opciones avanzadas permiten los 18 modelos. El modo automático
compara CPU y Vulkan mediante el runtime compartido y conserva una elección
medida; no se fuerza una GPU por el nombre del teléfono. El emulador permite
verificar CPU y los flujos, pero no medir la ventaja de Vulkan en un teléfono.

El [informe Android](docs/ANDROID_VALIDATION_20261120.md) documenta los APK,
el emulador, la evaluación real, las capturas y las limitaciones pendientes.
La [validación física del F8 Pro con Android 17](docs/F8_PRO_ANDROID17_VALIDATION_20261120.md)
incluye curso, teclado, datos conservados, descargas con pantalla apagada y
medidas CPU/Vulkan. Gemma eligió CPU y Qwen 4B Vulkan en ese ensayo; la decisión
continúa siendo medida por modelo y no una regla fija para ese teléfono.

Las actividades cuentan una vez como practicadas al comprobar una respuesta o
recibir feedback utilizable. No es necesario acertar para avanzar. Los aciertos
cerrados corresponden a la última práctica de cada ejercicio. El Writing no se
convierte en una nota numérica ni bloquea unidades.

## Modelos y opciones avanzadas

El modo equilibrado propone Qwen 3.5 4B Q4 en Windows cuando detecta Vulkan y hay
margen conservador de RAM. La propuesta es provisional. La calibración compartida
prueba CPU y distribuciones completas/parciales de GPU; acepta Vulkan con tres
muestras utilizables y una mejora mínima del 15 %. Para mantener Qwen como opción
automática se busca una mediana GPU de hasta 30 segundos. Si no cumple, se propone
Gemma E2B UD-Q4; MiniCPM 2B Q4 y LFM2.5 1.2B Q4 cubren memoria más limitada. Los 30
segundos no son un timeout de las respuestas del estudiante.

Una copia exacta disponible localmente puede evitar otra descarga; conserva su ID,
hash y procedencia. No se atribuyen a un GGUF de Unsloth los resultados de una
conversión local diferente. Las estimaciones no garantizan carga ni velocidad, y
no se descartan GPU integradas por su categoría.

**Opciones avanzadas** conserva el catálogo completo de la aplicación de prueba:
MiniCPM 2B F16/Q8/Q4; Qwen 4B local Q8/Q4 y Unsloth Q8/Q4; Gemma E2B QAT-Q4,
UD-Q4 y UD-Q2; LFM2.5 1.2B BF16/Q8/Q4 y 2.6B Q8/Q4. Se añaden Qwen 3.5 2B de
Unsloth Q4_K_M, Q8_0 y UD-Q4_K_XL: **18 opciones** en total.

La extensión pertenece a `CourseModelCatalog`: combina las 15 entradas congeladas
con `Course.Core/Assets/extra-models.json`. No modifica el catálogo del experimento
de 200 casos. `scripts/write_extra_catalog.py` reproduce esos tres registros.

También permite CPU, Vulkan, adaptador, capas, contexto 2048/4096 y uno a tres
intentos de formato. Una elección manual no cambia de modelo por su cuenta. Fijar
capas y adaptador exige confirmación del reparto exacto por el worker; un fallo
no se sustituye silenciosamente por CPU. Dejar las capas vacías usa la estimación.
Thinking se desactiva en el runtime donde se puede controlar. Se conservan los
prompts y parámetros interactivos vigentes. Los reintentos usan semillas 42/43/44,
solo para salidas no utilizables; no eligen por calidad ni repiten errores técnicos.

El **Laboratorio de Writing** permite tareas A1/A2, ejemplos y una simulación de
JSON inválido. Se identifica y queda fuera del progreso del curso.

## Datos y compatibilidad

- Progreso: `%LOCALAPPDATA%/WritingApp/Course/course.db` (SQLite, esquema 1).
- Android: `files/Course/course.db`, `files/models` y `files/sessions` dentro del
  espacio privado persistente de la misma aplicación; no son carpetas de caché.
- Modelos: `%LOCALAPPDATA%/WritingApp/Models`; en el checkout también se reutiliza
  la junction `SLM_A1A2/models` existente, sin copiarla.
- Runtime/perfiles: se conservan los directorios del prototipo bajo `WritingApp`.
- `--data-dir RUTA` permite aislar el progreso de una prueba; no cambia los modelos.
- Los respaldos ZIP contienen una copia SQLite consistente, versión y SHA-256.
  No contienen modelos ni calibraciones específicas del equipo. Restaurar requiere
  confirmación en la app y deja una copia automática de la base anterior.
- Historial completo en JSON y resumen CSV. Cada RAW recibido se guarda antes de
  interpretarlo; una interrupción conserva el borrador y los intentos anteriores.
- Las sesiones antiguas del prototipo permanecen en sus carpetas; no se convierten
  en actividades completadas.

## Compilar y verificar

Desde esta carpeta, con SDK **11.0.100** y los activos nativos existentes:

```powershell
dotnet build WritingCourse.slnx -c Release
dotnet run --project Course.Tests -c Release -- --report artifacts/verification/core-tests.json
dotnet run --project Course.UiTests -c Release -- --report artifacts/verification/ui-tests.json
.\scripts\windows_publish.ps1
```

Con el workload Android .NET 11, SDK Android 37.0 y JDK 21 de Android Studio:

```powershell
.\scripts\android_publish.ps1 -Runtime android-arm64
.\scripts\android_publish.ps1 -Runtime android-x64 -Automation
.\scripts\start_android_emulator.ps1
python scripts/verify_android_emulator.py --serial emulator-5580
python scripts/verify_android_emulator.py --serial emulator-5580 --mode resume
```

El controlador rechaza seriales de teléfonos. El AVD separado usa la imagen
Android 16 x64 ya instalada, 4 GiB de RAM y 16 GiB de almacenamiento; conserva el
AVD original. La variante `-Automation` incluye un arnés exportado y depuración,
usa solo ejemplos del curso y no se entrega a usuarios. El APK normal excluye
ese arnés y desactiva depuración. Los modelos se transfieren desde el repositorio
local y la aplicación verifica su SHA; estas pruebas no ejecutan benchmarks.

El build no descarga modelos. Para la comprobación real, separada de los benchmarks:

```powershell
dotnet run --project Course.Smoke -c Release -- --execute --matrix --output artifacts/verification/course-examples
```

Ese comando usa solo los seis ejemplos de las tres actividades de Writing:
Gemma/Qwen, CPU/Vulkan, 24 generaciones de integración y un intento por entrada.
Exige pesos locales exactos, no abre ni ejecuta los conjuntos de 40/120/200, y no
ajusta prompts según las salidas. Los resultados de formato y los errores del
modelo se informan por separado de los tests de software.

Para verificar adicionalmente la descarga, el SHA y una generación CPU del Qwen 2B
Q4 nuevo, existe `--execute --qwen2-readiness`. Ese modo puede descargar 1,28 GB si
no está preparado. No es una evaluación de precisión de ese modelo. La matriz
devuelve código 1 si hay salidas no utilizables, aunque su manejo seguro en la
aplicación haya funcionado; consulta el informe en lugar de contar ese código como
un fallo de compilación.

La arquitectura mantiene bindings compilados, JSON source generation y ausencia
de un contenedor por reflexión. El paquete actual usa JIT, sin trimming ni
NativeAOT; es preparación para AOT, no una certificación de compatibilidad AOT.
SQLite se ejecuta en una cola fuera del hilo de interfaz.

Los fuentes, pruebas, contenido y documentación se guardan en Git local. Binarios,
SQLite personales, modelos, RAW técnicos y cachés quedan excluidos. El prototipo
0.1.6 y los artefactos experimentales se conservan; no se configura ningún remoto.

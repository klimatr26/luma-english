# Writing local · Prototipo de demostración

Aplicación Windows Forms en C#/.NET 10 para mostrar el flujo de Writing A1/A2: ejercicio → respuesta → inferencia local → interpretación JSON → corrección y retroalimentación. Los ejercicios son nuevos y separados de los benchmarks. No es una nueva corrida de evaluación ni una certificación de calidad pedagógica.

## Abrir y presentar

Abre `publish/vulkan_20261109/WritingDemo.WinForms.exe` para la versión actual. La aplicación busca el proyecto desde su ubicación; en este equipo utiliza el junction `SLM_A1A2/models`, que apunta a `D:/SLM_A1A2_models`. Conserva las publicaciones anteriores en sus carpetas.

1. Selecciona el modelo, su cuantización y **Aceleración**. El modo inicial es **Auto Vulkan/CPU**. Pulsa **Cargar modelo**. Se comprueban tamaño y SHA-256 antes de iniciar llama.cpp. Solo se mantiene un modelo en memoria.
2. Selecciona un ejercicio A1 o A2. Puedes editar la consigna, escribir una respuesta o pulsar **Usar ejemplo correcto / incorrecto**. Cargar un ejemplo no ejecuta ni predetermina la evaluación.
3. Pulsa **Evaluar respuesta**. El panel muestra la afirmación del modelo: ✓ correcto, ✕ con errores o una advertencia si el formato o los campos impiden una interpretación consistente.
4. Revisa texto corregido, retroalimentación y ediciones. **JSON generado** conserva la respuesta textual exacta; **Ejecución local** muestra el runtime y permite cambiar la carpeta de modelos o indicar un token de descarga opcional.
5. **Guardar sesión** exporta una evidencia JSON de esta interacción. Las interacciones también quedan registradas localmente en `../logs/writing_demo/`, fuera de Git y de los resultados experimentales. Evita introducir información personal si no deseas conservarla allí.

La marca refleja `is_correct`, no una comparación oculta con el ejemplo ni un juicio humano. Un modelo puede equivocarse al evaluar inglés. Las contradicciones del contrato se presentan como advertencias, sin reemplazar la salida por la respuesta esperada.

## Aceleración Vulkan y CPU

| Modo | Comportamiento |
|---|---|
| Auto Vulkan/CPU | Consulta dispositivos, intenta Vulkan y confirma capas asignadas a GPU en el log propio. Ante ausencia o fallo técnico de arranque, intenta CPU una vez antes de generar. |
| Vulkan | Exige un dispositivo Vulkan y offload confirmado; presenta el fallo si no puede cargar. |
| CPU | Fuerza `--device none -ngl 0 --no-kv-offload --no-op-offload`. |
| CUDA anterior | Usa el runtime CUDA preservado y su comprobación original del ejecutable. |

La interfaz y las sesiones exportadas muestran el backend efectivo, dispositivo lógico, capas offload y motivo de fallback. Cambiar de modo exige volver a cargar el modelo. No se repite una respuesta por CPU cuando el modelo produce JSON inválido, una evaluación incorrecta o falla una generación; HTTP 429 detiene la ejecución propia.

El paquete oficial Vulkan b11457 está separado en `../tools/llama.cpp/b11457-vulkan/`, con manifiesto de procedencia `../manifests/demo_vulkan_runtime_20261109.json`. La aplicación comprueba el manifiesto fijado y sus 52 archivos; rechaza DLL/EXE adicionales. Incluye los plugins CPU y no distribuye DLL CUDA ni un driver Vulkan. Windows necesita un driver que exponga Vulkan compatible para usar GPU; sin él, Auto intenta CPU. No hace falta instalar el SDK Vulkan para ejecutar este paquete.

Si se traslada el checkout a otro equipo y falta el paquete, prepararlo desde la raíz del repositorio con `python SLM_A1A2/demo/scripts/acquire_vulkan_runtime.py --restore-pinned`. Este modo verifica el manifiesto de esta entrega, descarga el ZIP fijado, comprueba sus hashes y restaura el directorio sin cambiar el manifiesto ni reemplazar una carpeta existente. El modo sin ese flag sirve para una adquisición inicial con manifiesto nuevo y requiere una revisión del pin antes de usarla en C#. La descarga del runtime no se confunde con **Descargar / preparar**, que gestiona los pesos GGUF.

La justificación, incidencias, pruebas y límites para Android están en [la integración Windows](../documentation/vulkan_windows_integration_20261109.md) y [las notas Android](../documentation/vulkan_android_integration_notes_20261109.md).

## Modelos y archivos

El catálogo toma las identidades, tamaños, hashes y parámetros del manifiesto experimental preservado. Incluye 13 configuraciones:

Las fuentes descargables están fijadas en [`model_sources.json`](model_sources.json): repo, revisión, archivo remoto y SHA-256/tamaño cotejados con los árboles HF guardados localmente. El catálogo usa ese archivo pequeño y no necesita que la caché `models/` esté presente para arrancar. Qwen 4B queda marcado como conversión local sin URL GGUF.

| Modelo | Variantes |
|---|---|
| Qwen3.5-4B | Q8_0, Q4_K_M |
| MiniCPM5-2B | F16, Q8_0, Q4_K_M |
| Gemma 4 E2B | Google QAT Q4_0, Unsloth UD-Q4_K_XL, UD-Q2_K_XL |
| LFM2.5-1.2B | BF16, Q8_0, Q4_K_M |
| LFM2.5-2.6B | Q8_0, Q4_K_M |

Las variantes no tienen la misma calidad ni las mismas necesidades de memoria. Gemma UD-Q2 y algunas salidas LFM presentaron problemas de estructura en desarrollo; se conservan para demostrar también esos límites. Los nombres UD no implican un único formato de tensor. Qwen4B/MiniCPM/Gemma son familias preseleccionadas provisionalmente; no se declara que sus cuantizaciones hayan ganado todas las métricas.

Si falta un archivo, **Descargar / preparar** obtiene el artefacto fijado por revisión y comprueba su SHA antes de usarlo. Los archivos presentes no se vuelven a descargar y un archivo incorrecto no se reemplaza automáticamente. Los GGUF descargados se escriben primero como parciales separados; no se carga un parcial. Puedes cancelar y cambiar la carpeta de destino. Se necesita espacio libre suficiente y conexión únicamente durante la adquisición.

Qwen4B es un caso distinto: los GGUF usados se convirtieron localmente y no se inventa una URL para esos bytes. La preparación recupera los archivos fuente de la revisión fijada, usa el conversor b11457 ya disponible con `--no-nextn`, genera el F16 intermedio y cuantiza a Q8_0 o Q4_K_M. Requiere las herramientas y `.venv` originales del proyecto, bastante más espacio que el GGUF final y más tiempo que una descarga directa. La receta y hashes de referencia están en `manifests/qwen_conversion_record_120.json`. Si ya existe el GGUF correcto, no se ejecuta la conversión.

El token opcional de Hugging Face permanece en memoria durante la sesión; no se guarda en la evidencia. Cuando un proveedor exige acceso, licencia o autenticación, debes gestionarlo con el proveedor y aportar un token autorizado. La aplicación no acepta contratos en tu nombre. Las etiquetas de licencia reproducen el manifiesto; LFM está registrado como `lfm1.0`.

## Parámetros y manejo de salida

Se reutilizan el system prompt canónico y los parámetros registrados por familia: contexto 4096, máximo 512 tokens de salida, semilla 42, plantillas nativas, `--reasoning off`, presupuesto de razonamiento 0 y `enable_thinking=false` donde hay control nativo. No hay grammar JSON, reintentos por mala respuesta ni sustitución silenciosa de modelo. El contenido de razonamiento no vacío se trata como un problema de ejecución.

El parser diferencia JSON estricto, JSON recuperado de una envoltura, JSON inválido, contrato inválido y campos incoherentes. Rechaza claves duplicadas, tipos incorrectos y claves inesperadas. El RAW se preserva. La recuperación no convierte la salida original en JSON estricto ni se contabiliza como mejora del benchmark. El límite de tokens se muestra cuando la API informa truncamiento.

Las cajas de texto adaptan los saltos de línea a Windows para mostrarlos correctamente. Los registros conservan las cadenas originales; la adaptación visual no interviene en el parser ni en la clasificación.

## Compilar y probar

En `SLM_A1A2/demo`:

```powershell
dotnet publish WritingDemo.WinForms/WritingDemo.WinForms.csproj -c Release --no-self-contained -o publish
dotnet run --project WritingDemo.FeedbackTests/WritingDemo.FeedbackTests.csproj
dotnet run --project WritingDemo.AssetTests/WritingDemo.AssetTests.csproj
python -B scripts/test_prepare_qwen_demo.py
dotnet run --project WritingDemo.RuntimeTests/WritingDemo.RuntimeTests.csproj
```

`Compilar_y_abrir.ps1` compila y abre la aplicación. La selección de SDK está fijada en `global.json` a la versión estable instalada 10.0.402; el ejecutable requiere .NET 10 Desktop Runtime. No hay dependencias NuGet de terceros. Se eligió [Windows Forms](https://learn.microsoft.com/dotnet/desktop/winforms/overview/) para usar los controles de escritorio disponibles en este Windows sin instalar un framework adicional.

Para la entrega Vulkan usa `Compilar_vulkan_y_abrir.ps1`, que publica en una carpeta separada:

```powershell
dotnet publish WritingDemo.WinForms/WritingDemo.WinForms.csproj -c Release --no-self-contained -o publish/vulkan_20261109
dotnet run --project WritingDemo.PromptTests/WritingDemo.PromptTests.csproj
python -m unittest discover -s scripts -p "test_*.py"
```

`WritingDemo.BackendSmoke` exige `--execute` y realiza una generación de un ejercicio nuevo por modelo seleccionado. `--backend AutoVulkanCpu|Vulkan|Cpu|ExistingCuda` controla el motor; `--hide-vulkan-devices` es exclusivamente diagnóstico y oculta las GPUs al hijo mediante un entorno local. `--load-only` comprueba carga/health/offload sin enviar una petición de chat; llama.cpp puede hacer su warmup interno normal. Sus evidencias nunca sobrescriben un archivo existente ni se incorporan al benchmark. Cancelación y HTTP 429 guardan la incidencia y detienen la secuencia.

`WritingDemo.Smoke` realiza **inferencias nuevas de demostración**, con ejemplos de `ExerciseCatalog`, y por eso se ejecuta de forma explícita y separada de las pruebas unitarias. Nunca recorre ni escribe los benchmarks. Sus registros locales no se importan como evaluación humana.

La verificación y los resultados de esta entrega se documentan en `../documentation/local_demo_20261016.md`.

## Revisión de instrucciones del 9 de noviembre

La versión nueva se encuentra en `publish/review_20261109/WritingDemo.WinForms.exe`. Añade **Modo de retroalimentación**: el prompt base y un ajuste derivado de la revisión del investigador para Qwen4B, MiniCPM y Gemma, etiquetado **pendiente de validar**. LFM mantiene el base. El modo revisado permite consejos opcionales de escritura en `feedback`, sin llamar error a una expresión válida ni cambiar el texto correcto. Las sesiones registran el perfil y el SHA del prompt usado. El ajuste no se ha evaluado mediante inferencias nuevas y no cambia los benchmarks.

La configuración está en `prompts/human_review_20261109.json`; la trazabilidad y sus límites, en [el seguimiento de revisión](../documentation/human_review_prompt_followup_20261109.md). Para compilar esta versión sin reemplazar la anterior:

```powershell
dotnet publish WritingDemo.WinForms/WritingDemo.WinForms.csproj -c Release --no-self-contained -o publish/review_20261109
dotnet run --project WritingDemo.PromptTests/WritingDemo.PromptTests.csproj
```

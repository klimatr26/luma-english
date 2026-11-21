# Auditoría estática de preparación y readiness — versión actual

**Alcance:** lectura estática de los cuatro scripts listados abajo y lectura de sus manifiestos de procedencia relevantes. No ejecuté scripts, servidores, generación ni descargas. No edité ninguno de los cuatro scripts.

| Script revisado | SHA-256 |
|---|---|
| `scripts/prepare_experiment_120.py` | `808A3174858E6570825ED7398E18B044C29756D590C955FE61706FC191DCCC7D` |
| `scripts/check_readiness_120.py` | `EFAE546D2FB4579349893A5F1EEF12A2625C34CB817D2BFD86243100D5B8F546` |
| `scripts/write_model_inventory.py` | `460FE50410CBB665FE89A58319A88E13F4B74F4CAE51EBE6D3C8AFD6CA95DD06` |
| `scripts/compare_native_templates_120.py` | `094CBF1E966B1A4AF020205CBE90683E2AE3B759AEFFA08D5F832A0B27215297` |

## Controles confirmados

- El manifest requiere 16 IDs únicos. Los hashes GGUF computados ahora sin un registro verificado quedan `present_unverified`; no son aceptados como listos. Para los artefactos no-Qwen, el SHA de inventory se acepta solo con tamaño/hash upstream coincidentes, hash estable, mismo archivo, tamaño y `hf_commit` igual a la revisión declarada. En el estado leído, las 11 configuraciones no-Qwen coinciden en commit, tamaño, SHA y estabilidad. El flujo Qwen compara las fuentes y el converter con pins, comprueba la presencia de la implementación Qwen3.5 y valida las salidas convertidas frente a inventory y record.
- Readiness vuelve a calcular el SHA del modelo y de `llama-server.exe` inmediatamente antes del lanzamiento. El manifest se hashea al cargar y se comprueba durante y al final de la ejecución. Una diferencia de hash invalida readiness.
- La ruta de generación es secuencial, exige health `200/status=ok`, render y tokenización del render, CUDA y un conteo positivo de capas en GPU; los errores HTTP 429 abortan la corrida. Hay un único request sintético por configuración y un marker global impide repetir una generación ya registrada. Los logs de servidor se crean de forma exclusiva, y `--out-dir` exige un directorio bajo `logs` y rechaza logs previos en esa ruta.
- Se verifica el hash nativo del render sintético dentro de cada grupo de cuantización en la corrida completa. El script offline de templates documenta cinco probes sintéticos para Gemma y limita su conclusión a esos renders, sin sustituir el gate nativo.
- La auditoría de inventory detecta desajustes explícitos de tamaño/SHA y cambios de tamaño o mtime durante el hash. No observé un desajuste en el inventory actual leído.

## Observaciones pendientes o límites

1. **P2 — salida de `--config` puede confundirse con readiness completa.** El JSON resumido marca `complete_matrix: false` y cambia `ready` a `diagnostic_only_not_full_matrix`, pero `logs/readiness_120.json` y el Markdown se escriben con el estado original `ready`; además, el modo diagnóstico sobrescribe los mismos informes raíz que usa la corrida completa. Separar los destinos del modo `--config` o etiquetar todos sus informes como diagnósticos preservaría la evidencia canónica. La comprobación de grupo no tiene comparador en una ejecución aislada, así que ese modo no debe usarse como prueba de equivalencia entre cuantizaciones. En una corrida completa que aborta o se detiene por error, `complete_matrix` también puede quedar `true` porque se añaden filas `skipped_*` hasta llegar a 16; los estados muestran el fallo, pero el campo debería significar explícitamente “16 configs listas” o llamarse “16 filas representadas”.

2. **P2 — el record Qwen no fija el hash del cuantizador usado.** El preparador valida el hash actual del script converter y verifica que el texto del recipe declare `llama-quantize.exe F16 Q8_0/Q4_K_M`; `runtime_asset_hashes_120.json` también contiene el SHA del binario `llama-quantize.exe`, pero el record de conversión y el gate del preparador no lo enlazan. Los bytes de salida sí se contrastan con inventory y record. Para una cadena de procedencia reproducible, conviene agregar `quantizer_sha256` al record y compararlo con el runtime pin.

3. **P2 — `write_model_inventory.py --strict` no significa “todo verificado”.** Su lista de `mismatches` solo incluye valores explícitamente `False`; una raíz ausente, una referencia faltante (`None`) o una conversión añadida a `unverified_conversions` puede dejar exit code cero. El preparador posterior falla cerrado y deja esos modelos sin verificar, por lo que el gate completo no se elude; aun así, el exit code de inventory no debería interpretarse por sí solo como verificación completa.

4. **Límite de alcance — igualdad de template por probe.** Readiness compara el SHA del render nativo para un único texto sintético por cuantización. Eso prueba igualdad en esa entrada y no equivalencia lógica de ramas dinámicas del template. El reporte incluye la probe y los hashes; si se necesita cubrir ramas de system/multi-turn/tool, deben añadirse renders sintéticos adicionales antes de afirmar esa cobertura.

## Estado operativo observado

El workspace conserva logs del primer intento en `logs/readiness`; el preflight actual rechaza de forma explícita una ruta `--out-dir` que ya contenga esos logs y comprueba globalmente que no haya request markers previos. Usar un directorio técnico nuevo bajo `SLM_A1A2/logs`. La revisión no confirma readiness ni generación: el primer intento reportado se detuvo antes de generar, y esta auditoría no lo reejecutó.

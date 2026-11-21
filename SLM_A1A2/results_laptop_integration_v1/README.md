# Evidencia integrada del portátil

La conclusión vigente está en [el informe conjunto](../documentation/laptop_results_integration_20261118.md). `comparison.csv` reúne los catorce bloques/intentos registrados en los cinco manifiestos de ejecución, incluido el segundo fallo técnico de Qwen. Hay 165 respuestas satisfactorias y 15 textos únicos de desarrollo; la simulación de VRAM y la prueba de batería son sesiones separadas.

La auditoría se conserva en [el registro JSON](../manifests/laptop_integration_audit_20261118.json). La entrada original de cada archivo figura en [el inventario de importación](../manifests/laptop_integration_import_20261118.json). Los RAW, la telemetría y los binarios se conservan locales, sin añadirlos a Git.

`laptop_20261118_evidence.zip` conserva la evidencia importada y los archivos necesarios para su auditoría desde una copia extraída con la misma estructura de carpetas. Incluye las DLL congeladas y experimentales como evidencia local. No contiene modelos GGUF, entornos virtuales, credenciales ni `.git`. Los ejecutables de las sondas diagnósticas no estaban en la copia suministrada. El SHA-256 del ZIP y el listado de entradas están en [el manifiesto del paquete](../manifests/laptop_evidence_bundle_20261118.json), fuera del ZIP para evitar una referencia circular.

La auditoría usa únicamente la biblioteca estándar de Python:

```powershell
python SLM_A1A2/scripts/audit_laptop_results.py
```

Ese comando comprueba archivos y métricas, sin iniciar inferencias. No ejecutar los runners archivados para consultar los resultados. Los datos originales y sus manifiestos no se sustituyeron por los resúmenes de esta carpeta.

# Criterio de cuantización — desarrollo 120

La justificación completa y sus fuentes fijadas están en
[`manifests/quantization_rationale_120.md`](manifests/quantization_rationale_120.md).

- F16/BF16: referencia de pesos de las familias pequeñas; Q8_0: ancla PTQ de
  alta fidelidad; Q4_K_M: punto de equilibrio de tamaño y precisión esperada.
- Q4_K_M mezcla formatos por tensor y no significa que todos los pesos sean
  de cuatro bits. Las asignaciones concretas deben registrarse por GGUF.
- Gemma Google QAT Q4_0 y Unsloth Dynamic UD-Q4_K_XL/UD-Q2_K_XL tienen
  procedencia y codificación distintas; no se agrupan como Q4_K_M estándar.
- Los resultados de fabricante son hipótesis, no resultados de este estudio.
  Comparar familias o fuentes diferentes no aísla causalmente la cuantización.
- El F16 intermedio de Qwen 4B se conserva sin probar y no añade una
  configuración: la matriz ampliada tiene exactamente 16.
- LFM2.5-2.6B añade Q8_0/Q4_K_M oficiales PTQ para los 120 y una futura
  extensión separada de los 40 casos. No se añade referencia F16 ni QAD.

No hay todavía resultados principales ni mediciones de calidad de estos 120.

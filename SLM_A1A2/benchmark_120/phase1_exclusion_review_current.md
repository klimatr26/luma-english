# Comparación y exclusión de Fase 1 — fuentes actuales

Fase 1 SHA256: a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9

Comparaciones: 11940 (7140 dentro de 120, 4800 contra los 40).
Métodos: igualdad tras normalización, SequenceMatcher, trigramas Jaccard y containment. Umbrales: 0.60/0.30/0.55.
Candidatos finales sobre umbral: 0.

La revisión de IA examinó además los veinte pares más cercanos. El caso A1-E040 se reescribió porque repetía el patrón narrativo del antiguo A1-E12 aun bajo el umbral; A1-E012 se diversificó del nuevo A1-E026. No se cambió la Fase 1.
Los pares restantes comparten vocabulario cotidiano, formas gramaticales o actos comunicativos, pero sus proposiciones y detalles son distintos. Ejemplos: cuenco de uvas/pera frente a existencias de cocina y compras; horas del padre/lugares visitados frente a residencia/edad del hermano; clases en granja frente a paseo familiar de playa.
No se presenta esta pantalla léxica ni el juicio de IA como prueba matemática de ausencia de paráfrasis semánticas. No se afirma procedencia histórica demostrada de cada borrador.

| Fuente | Caso | Otro caso | Ratio |
|---|---|---|---|
| within_120 | A1-E017 | A1-E032 | 0.5854 |
| against_40 | A1-E019 | A1-E13 | 0.5538 |
| within_120 | A1-C006 | A1-E017 | 0.5480 |
| within_120 | A1-E032 | A1-E037 | 0.5000 |
| within_120 | A1-C005 | A1-E018 | 0.4862 |
| against_40 | A1-E003 | A1-C03 | 0.4836 |
| against_40 | A1-C007 | A2-E14 | 0.4798 |
| against_40 | A1-E001 | A2-E04 | 0.4789 |
| against_40 | A1-E010 | A1-E13 | 0.4788 |
| against_40 | A1-C002 | A2-E14 | 0.4717 |
| against_40 | A1-E044 | A2-E04 | 0.4689 |
| within_120 | A1-E021 | A1-E044 | 0.4681 |
| within_120 | A1-E013 | A1-E023 | 0.4677 |
| within_120 | A1-E026 | A1-E041 | 0.4640 |
| against_40 | A1-E008 | A1-E11 | 0.4636 |
| against_40 | A1-E035 | A1-E14 | 0.4622 |
| against_40 | A1-E038 | A1-E13 | 0.4622 |
| within_120 | A1-C006 | A1-E005 | 0.4573 |
| within_120 | A1-E031 | A2-E032 | 0.4570 |
| against_40 | A1-E039 | A1-E04 | 0.4569 |

Fuentes SHA256:
- A1_cases.json: e2b7075b3db86d75a44f8a1accaa771359a7d44dd5ab4e570b470d7ccf56f50c
- A2_cases.json: ed40ec9181e340fb86e55f331cca98f2acb5b03f3bf4bda99b0b37340e811279

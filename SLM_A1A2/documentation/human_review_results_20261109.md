# Revisión del investigador — ingreso del 9 de noviembre de 2026

**Estado: provisional; pendientes aclaraciones del investigador.** No se han corregido notas ni importado una capa humana definitiva.

Se recibieron 180 fichas: 60 mismos casos × tres configuraciones. Revisor declarado: `kevin-01`. Las fichas declaran fecha `2026-10-19`; la recepción es del 9 de noviembre. La fecha del archivo es de exportación y no demuestra cuándo se realizó cada juicio.

SHA-256 del respaldo original: `91a638c9725894144a0b1307af9441c9eca2e40b6423263ab71a454e2b4dd24e`. El paquete, crosswalk, respuestas y filas v2 quedaron vinculados y verificados. Hay 6 conflictos del contrato humano y 3 propuestas INVALID_CASE.

## Puntuaciones tal como fueron introducidas

La puntuación de cada ficha es la media de sus criterios numéricos 0–2; NA no equivale a cero. La media del modelo da igual peso a cada ficha con alguna nota aplicable. El equivalente /100 es esa media ×50: son puntos de rúbrica, **no porcentaje de precisión**. Se publica aparte la cobertura. Esta tabla conserva incluso las notas cuya aplicabilidad está pendiente; no es el cierre validado.

| Configuración | Media 0–2 | Puntos /100 | Fichas con nota /60 | CORRECT | PARTIAL | INCORRECT | INVALID_CASE |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5-4B Q4_K_M | 1.9122 | 95.6111 | 60/60 | 52 | 4 | 2 | 2 |
| Gemma E2B UD-Q4_K_XL | 1.8283 | 91.4167 | 60/60 | 48 | 6 | 5 | 1 |
| MiniCPM5-2B Q4_K_M | 1.7497 | 87.4859 | 59/60 | 41 | 11 | 8 | 0 |

MiniCPM tiene una ficha marcada no evaluable, con todas las notas NA: se conserva su veredicto, pero no se inventa una puntuación. Las medias son condicionales a las fichas con nota; no ocultan esa falta de cobertura.

## Comparación provisional en casos comunes sin pendientes

Se omiten analíticamente de los tres modelos los mismos casos con conflictos de aplicabilidad o propuestas de invalidación no resueltas. Esto **no invalida** el benchmark ni modifica sus puntuaciones históricas; evita comparar modelos en casos diferentes mientras se aclaran las fichas.

Casos apartados temporalmente: `A1-C006`, `A2-C001`, `A2-C003`, `A2-C008`, `A2-C010`, `A2-C013`, `A2-C014`.

| Configuración | Fichas comparadas | Fichas con nota | Media 0–2 | Puntos /100 | CORRECT / comparadas |
|---|---:|---:|---:|---:|---:|
| Qwen3.5-4B Q4_K_M | 53 | 53 | 1.9226 | 96.1321 | 48/53 |
| Gemma E2B UD-Q4_K_XL | 53 | 53 | 1.8736 | 93.6792 | 44/53 |
| MiniCPM5-2B Q4_K_M | 53 | 52 | 1.7468 | 87.3397 | 35/53 |

## Criterios en la comparación común

Cada celda indica media 0–2 y número de notas numéricas (n). No se equiparan los denominadores ni se transforma NA en éxito.

| Criterio | Qwen4B Q4 | Gemma UD-Q4 | MiniCPM Q4 |
|---|---:|---:|---:|
| `detection` | 1.9000 (n=30) | 1.7667 (n=30) | 1.4667 (n=30) |
| `correction` | 1.9000 (n=30) | 1.6667 (n=30) | 1.4000 (n=30) |
| `meaning_preservation` | 1.9811 (n=53) | 2.0000 (n=53) | 1.9615 (n=52) |
| `level_appropriateness` | 2.0000 (n=53) | 1.9623 (n=53) | 1.9808 (n=52) |
| `grammatical_explanation` | 1.8302 (n=53) | 1.7925 (n=53) | 1.4231 (n=52) |
| `pedagogical_clarity` | 1.9245 (n=53) | 1.8679 (n=53) | 1.8077 (n=52) |
| `clean_text_handling` | 1.8696 (n=23) | 1.9130 (n=23) | 1.9545 (n=22) |

## Aclaraciones que impiden el cierre

Las fichas completas para revisar se encuentran en [casos pendientes](human_review_cases_pending_20261109.md). La siguiente lista conserva el veredicto y enumera errores de contrato; no decide lingüísticamente el caso ni reemplaza la revisión humana.

- `06-minicpm5-2b-q4-k-m` / `A1-C006` / `br-a7ebb5a7d231d1f96b2c4acf` — `CORRECT`. detection must be 'NA' for a correct-text control; correction must be 'NA' for a correct-text control; clean_text_handling must be 0, 1, or 2 for an assessable correct-text control
- `13-gemma4-e2b-ud-q4-k-xl` / `A2-C001` / `br-37fe38ffb4a2d3a592c3072c` — `CORRECT`. detection must be 'NA' for a correct-text control; correction must be 'NA' for a correct-text control; clean_text_handling must be 0, 1, or 2 for an assessable correct-text control
- `13-gemma4-e2b-ud-q4-k-xl` / `A2-C003` / `br-67ebb6cf58f204c9d1b2b81b` — `CORRECT`. detection must be 'NA' for a correct-text control; correction must be 'NA' for a correct-text control; clean_text_handling must be 0, 1, or 2 for an assessable correct-text control
- `11-qwen35-4b-q4-k-m` / `A2-C010` / `br-6c387cee83684e65184d3746` — `INVALID_CASE`. Propuesta de caso inválido pendiente de adjudicación.
- `11-qwen35-4b-q4-k-m` / `A2-C008` / `br-275d5b7e5d4e674060fc17ca` — `INVALID_CASE`. Propuesta de caso inválido pendiente de adjudicación.
- `11-qwen35-4b-q4-k-m` / `A2-C014` / `br-3ea9d9bb642cc426c073a910` — `CORRECT`. detection must be 'NA' for a correct-text control; correction must be 'NA' for a correct-text control; clean_text_handling must be 0, 1, or 2 for an assessable correct-text control
- `13-gemma4-e2b-ud-q4-k-xl` / `A2-C013` / `br-930f5c918cb6fb7df4cc9585` — `INVALID_CASE`. detection must be 'NA' for a correct-text control; correction must be 'NA' for a correct-text control; clean_text_handling must be 0, 1, or 2 for an assessable correct-text control
- `11-qwen35-4b-q4-k-m` / `A2-C013` / `br-f1a74afb9b236138b2f3284c` — `INCORRECT`. detection must be 'NA' for a correct-text control; correction must be 'NA' for a correct-text control; clean_text_handling must be 0, 1, or 2 for an assessable correct-text control

## Interpretación y límites

Qwen encabeza ambas medias descriptivas, seguido de Gemma y MiniCPM. No se afirma significación estadística, superioridad de toda la familia ni generalización a otras cuantizaciones: se revisaron solo estas tres configuraciones Q4, por un investigador y sobre una muestra enriquecida en controles (30 correctos/30 incorrectos), frente a 30/90 en el desarrollo completo. No se combinan estos números con los F0.5 automáticos ni se multiplican muestras por el número de modelos.

Las observaciones de formato (Markdown, claves adicionales, JSON roto) se conservan aparte de las siete notas humanas: la rúbrica no incluye un criterio numérico de formato. Una ficha CORRECT con JSON recuperable no se convierte automáticamente en JSON estricto.

El investigador ha pedido admitir recomendaciones opcionales de escritura aun cuando no existan errores. Esa política se implementa prospectivamente en el perfil `human-review-20261109`, sin reescribir los resultados del prompt anterior. Una recomendación de estilo no debe activar is_correct=false ni incorporarse a errors. El consejo también debe ser lingüísticamente válido. Los veredictos INVALID_CASE existentes siguen siendo propuestas hasta aclarar si se refieren al caso o al comportamiento del modelo.

El prompt base, gold, RAW, resultados automáticos y archivo aportado permanecen intactos. No se han ejecutado inferencias nuevas ni se ha accedido al test final. Para el registro técnico y la propuesta de prompts véase [seguimiento de revisión y prompts](human_review_prompt_followup_20261109.md).

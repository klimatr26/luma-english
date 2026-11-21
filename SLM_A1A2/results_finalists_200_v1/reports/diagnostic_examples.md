# Ejemplos diagnósticos de la comparación de 200

Inspección cualitativa posterior por IA. Estos ejemplos se eligieron para explicar anomalías; no son una muestra representativa ni una revisión humana. No se modificaron referencias ni puntuaciones. La muestra aleatoria estratificada de 20 casos para revisión del investigador está en `researcher_review_sample.json`, con sus notas aún vacías.

## T200-A1-C006: falsa alarma sin modificación

El control describe una fuente con agua que sale por tres tubos. Es gramatical. Gemma/Vulkan conserva todo el texto, devuelve `is_correct=false` y declara una edición cuyo fragmento original y corrección son idénticos. Su explicación reconoce que la frase es gramatical y propone otras palabras por fluidez. El parser devuelve `INCONSISTENT`.

Qwen/Vulkan conserva el original, devuelve `true` y `errors=[]`. Su feedback todavía menciona el nivel A1, contrario a la preferencia de estilo del prompt; eso no invalida su corrección textual. El ejemplo explica por qué CFAR y CTMR miden cosas distintas: se puede inventar una alarma sin modificar el texto.

## T200-A1-C012: inferir requisitos que el texto no impone

El control dice que la persona muestra un mensaje al trabajador de una tienda para recoger un paquete. Mostrar una notificación con un código es una lectura válida. Ambos modelos/Vulkan marcan el original como incorrecto y conservan `corrected_text` idéntico. Qwen reclama una tarjeta de identificación y Gemma sugiere mostrar un paquete o carta. La situación no exige esas sustituciones. El parser detecta contradicción en ambos.

Qwen reduce las falsas alarmas en este conjunto, pero no las elimina: 6/50 controles en cada backend. Esas seis observaciones corresponden a los mismos 50 casos, no a dos muestras independientes.

## T200-A2-E052: texto acertado no garantiza explicación acertada

Qwen/Vulkan entrega el texto de referencia, añade `do` en la pregunta y corrige la negación de tercera persona. Pasa el parser y el proxy automático. Sin embargo, la explicación generaliza erróneamente que las preguntas con `be` o modales requieren `do`, y llama a `does` una forma de `be`. Las preguntas con `be` y los modales no siguen esa regla. La corrección aplicada a este verbo léxico es acertada; la regla explicada no lo es.

Gemma/Vulkan usa una pregunta de futuro con presente continuo, `What time are you leaving ...?`, que es gramatical, y añade puntuación innecesaria en otra frase. Esa formulación no estaba entre las referencias completas congeladas. Su penalización ERRANT mezcla diferencias respecto a la reparación mínima y diferencias de alineación; no debe interpretarse como que cada FP sea una nueva oración agramatical. No se añade una referencia después de observar la salida.

## T200-A2-E014: contradicción fuera del alcance del parser

El original contiene el doble comparativo `more warmer`. Se licenciaron antes de inferir las dos reparaciones, `warmer` y `more warm`. Qwen/Vulkan usa la segunda y pasa el proxy, pero su feedback pide emplear la primera. El parser comprueba estructura y coherencia básica entre booleano/texto/lista; no valida semánticamente cada explicación.

## Alcance

El proxy informado exige texto coincidente con una referencia completa, clasificación acertada y un JSON utilizable. No certifica cada edición declarada, explicación, consejo opcional o preferencia de estilo. La reconstrucción de declaraciones y las ediciones sin cambio se informan por separado. Los resultados favorecen a Qwen en esas configuraciones para corrección textual y contrato, conservando una necesidad de revisión del feedback.

Los datos completos están en los cuatro JSONL puntuados de esta carpeta. La [auditoría independiente de resultados por IA](independent_result_audit.md) verificó identidades, cobertura y cifras, sin aplicar nuevas notas humanas.

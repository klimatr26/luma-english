# Encargo para proponer un minicurso de inglés A1

Diseña un minicurso para mostrarle al tutor cómo Writing Lab evalúa ejercicios de inglés en el dispositivo. La app de demostración recibe una consigna y la respuesta escrita, ejecuta un modelo local y muestra su veredicto, el texto corregido, las ediciones y la retroalimentación. También indica si pudo interpretar el JSON devuelto por el modelo.

Usa A1 como alcance inicial. Propón un recorrido breve que se pueda mostrar en pocos minutos. Puedes consultar los descriptores de producción escrita del MCER como orientación para elegir situaciones cotidianas y consignas simples. [Descriptores del Consejo de Europa](https://www.coe.int/en/web/common-european-framework-reference-languages/cefr-descriptors-search).

## Qué preparar

- Propón unas tres unidades con una progresión clara. Para cada una, indica qué podrá hacer el estudiante, da una explicación breve con un ejemplo y plantea la práctica que conduce al Writing. Escribe las consignas, opciones y respuestas de los ejercicios en inglés sencillo. Puedes explicar el diseño en español.
- Incluye actividades de **opción única** y de **completar con una palabra**. Una escala orientativa es dos de cada tipo por unidad. Da a cada pregunta una sola respuesta válida y una explicación breve. En los huecos, da una pista explícita cuando el contexto permita varias palabras. Por ejemplo, indica el verbo base entre paréntesis si quieres que se escriba su forma conjugada.
- Cierra cada unidad con un **Writing de dos a cuatro frases** en una situación cotidiana. Incluye un ejemplo correcto, una variante que introduzca un solo error claro y su corrección de referencia. La consigna debe admitir distintas respuestas válidas. Usa inglés estándar y trata las preferencias de estilo como sugerencias.
- Describe qué vería el tutor al recorrer una unidad. Incluye una respuesta cerrada con corrección inmediata y una evaluación de Writing con retroalimentación del modelo. Para mostrar el estado de JSON inválido, describe una salida de prueba identificada como simulada, por ejemplo `{"is_correct":`. Distingue los resultados esperados de cualquier resultado medido.

## Entrega y formato

Entrega un único documento llamado **`propuesta_curso.md`**. Si trabajas fuera del repositorio, devuelve el Markdown completo para guardarlo en `SLM_A1A2/cross_demo/docs/curso_demo/propuesta_curso.md`. Incluye en el documento:

1. El recorrido de las unidades, sus objetivos y el flujo de demostración.
2. Un bloque cercado de JSON válido con todos los ejercicios y sus claves. Usa IDs únicos y estables, como `u01` para una unidad y `u01-opcion-01` para una actividad. El bloque debe tener un objeto raíz con `units`. Cada unidad incluye `id`, `title` y `activities`. Cada actividad incluye `id`, `type` y `prompt`.

| Valor de `type` | Campos adicionales |
|---|---|
| `single_choice` | `options` con objetos `id` y `text`. `answer` contiene el ID de la opción correcta. `explanation` explica la clave. |
| `one_word` | `prompt` contiene exactamente un hueco `____`. `answer` contiene la palabra en minúsculas y sin puntuación. `explanation` explica la clave. |
| `writing` | `level` con valor `A1`, `correct_example`, `incorrect_example` y `reference_correction`. Usa `prompt` para la consigna que recibirá el modelo. |

La comprobación propuesta para opción única compara el ID seleccionado con la clave. Para una palabra, elimina espacios externos y compara sin distinguir mayúsculas. En Writing se envían al modelo el nivel, la consigna y el texto escrito. Los ejemplos y la corrección de referencia sirven para preparar la demostración y quedan fuera del prompt como claves de evaluación. La interfaz puede mostrar el veredicto, las ediciones y la retroalimentación cuando el JSON es utilizable, o una advertencia con el estado del formato cuando falla.

Redacta ejercicios originales para la demo y trabaja con la información de este encargo. Antes de entregar, verifica que el bloque se pueda interpretar como JSON, que cada clave cerrada pertenezca al ejercicio y que la corrección de cada ejemplo de Writing conserve el sentido.

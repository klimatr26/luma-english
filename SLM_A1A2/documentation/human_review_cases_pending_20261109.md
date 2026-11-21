# Fichas pendientes de revisión humana

## Alcance

Este documento reúne seis fichas señaladas para aclarar la aplicación del contrato de revisión y dos fichas con veredicto `INVALID_CASE` en Qwen4Q4. Transcribe el respaldo del revisor, el texto del packet y la identidad coordinadora enlazada por `blind_output_id`. No cambia las notas, el veredicto, la bandera `original_has_errors` ni el rationale; tampoco propone una puntuación nueva ni adjudica los casos.

El respaldo registra `review_date: 2026-10-19` y `reviewer_id: kevin-01`. La fecha del nombre de este archivo no sustituye esa fecha de revisión. El hash de packet declarado por el respaldo es `abee26b77d9afe0b7d44cb25729b72aa1b0c5bab54f97635e7a6908b58d5a486`.

### Referencia neutral para los campos `NA`

La rúbrica v2 usa `NA` para indicar que un criterio no aplica o que no hay material evaluable, según su ancla. En controles correctos, el contrato requiere detección y corrección en `NA`; en casos con errores, requiere manejo de texto correcto en `NA`. Si `response_assessable=false`, requiere todas las notas y los dos juicios semánticos en `NA` y un rationale que explique la limitación. Estas reglas se consignan para leer las fichas; no determinan la verdad lingüística del caso ni autorizan a reemplazar una nota humana.

En las primeras seis fichas se pidió revisar una combinación concreta del respaldo: `original_has_errors=true` junto con notas numéricas de detección/corrección y `clean_text_handling=NA`, aunque la condición de referencia del caso es control. Las dos últimas fichas muestran los dos veredictos `INVALID_CASE` de Qwen indicados para aclaración. Los valores se presentan tal como están guardados.

### Regla prospectiva de estilo solicitada

Para futuras corridas, un texto gramaticalmente correcto puede recibir una sugerencia de estilo si la sugerencia es válida y no se etiqueta como error: conservar los cuatro campos JSON; usar `is_correct: true`, `errors: []` y `corrected_text` idéntico al original; si se incluye la sugerencia, iniciar `feedback` con `Optional writing suggestion (not an error)`. Una recomendación falsa no se acepta por ser estilística. Esta pauta prospectiva no se aplica retroactivamente a estas fichas ni modifica la rúbrica o los seis registros pendientes.

## Fichas

### 1. Conflicto de aplicabilidad indicado: MiniQ4 · A1-C006

- `blind_output_id`: `br-a7ebb5a7d231d1f96b2c4acf`
- `config_id`: `06-minicpm5-2b-q4-k-m`
- `case_id`: `A1-C006`
- `scope`: `results_120`
- Nivel: `A1`
- `original_has_errors` (campo auxiliar del respaldo): `true`
- `response_assessable`: `true`

**Consigna**

Describe the clothes you wear on a cold day.

**Texto original del estudiante**

````text
When it is cold, I wear my green coat and warm gloves. My boots are under the chair near the door. I put them on before I leave for the bus in the morning.
````

**Respuesta íntegra del modelo, copiada del packet**

````text
{
  "is_correct": true,
  "corrected_text": "When it is cold, I wear my green coat and warm gloves. My boots are under the chair near the door. I put them on before I leave for the bus in the morning.",
  "errors": [],
  "feedback": "The student's text is correct. No grammatical, spelling, punctuation, or lexical errors were found."
}
````

**Registro humano vigente**

- Revisor/fecha declarados en la ficha: `kevin-01` / `2026-10-19`
- `original_has_errors`: `true`
- `response_assessable`: `true`
- Detección (`detection`): `2`
- Corrección (`correction`): `2`
- Preservación del significado (`meaning_preservation`): `2`
- Adecuación al nivel (`level_appropriateness`): `2`
- Explicación gramatical (`grammatical_explanation`): `2`
- Claridad pedagógica (`pedagogical_clarity`): `2`
- Manejo de texto correcto (`clean_text_handling`): `NA`
- `meaning_preserved`: `true`
- `explanations_ok`: `true`
- Veredicto: `CORRECT`

**Rationale íntegro**

````text
Se refiere al "texto del estudiante". Otras retroalimentaciones han hablado con el estudiante, como expresarle un buen trabajo, mientras que esta le habla al evaluador.
````

### 2. Conflicto de aplicabilidad indicado: GemmaUDQ4 · A2-C001

- `blind_output_id`: `br-37fe38ffb4a2d3a592c3072c`
- `config_id`: `13-gemma4-e2b-ud-q4-k-xl`
- `case_id`: `A2-C001`
- `scope`: `results_120`
- Nivel: `A2`
- `original_has_errors` (campo auxiliar del respaldo): `true`
- `response_assessable`: `true`

**Consigna**

Describe a small change that made your journey to school easier.

**Texto original del estudiante**

````text
Since the new bridge opened, my walk to school has been much shorter. I used to cross a busy road, but now I can follow a quiet path beside the canal. On rainy days, I still take the bus because the path gets muddy. The bridge is useful for people who live on both sides of town.
````

**Respuesta íntegra del modelo, copiada del packet**

````text
{
  "is_correct": true,
  "corrected_text": "Since the new bridge opened, my walk to school has been much shorter. I used to cross a busy road, but now I can follow a quiet path beside the canal. On rainy days, I still take the bus because the path gets muddy. The bridge is useful for people who live on both sides of town.",
  "errors": [],
  "feedback": "Your text is grammatically correct and very clear for an A2 level."
}
````

**Registro humano vigente**

- Revisor/fecha declarados en la ficha: `kevin-01` / `2026-10-19`
- `original_has_errors`: `true`
- `response_assessable`: `true`
- Detección (`detection`): `2`
- Corrección (`correction`): `2`
- Preservación del significado (`meaning_preservation`): `2`
- Adecuación al nivel (`level_appropriateness`): `2`
- Explicación gramatical (`grammatical_explanation`): `2`
- Claridad pedagógica (`pedagogical_clarity`): `2`
- Manejo de texto correcto (`clean_text_handling`): `NA`
- `meaning_preserved`: `true`
- `explanations_ok`: `true`
- Veredicto: `CORRECT`

**Rationale íntegro**

````text
"very clear for an A2 level" puede tanto motivar a algunos como potencialmente atacar a otros (en pocos casos, me imagino); en todo caso, suena a un modelo repitiendo instrucciones (como "evalúa este texto de nivel A2") y no tanto algo que diría un profesor a menos que tuviera confianza con el alumno. Aun así, en general, no me parece una retroalimentación necesariamente mala.
````

### 3. Conflicto de aplicabilidad indicado: GemmaUDQ4 · A2-C003

- `blind_output_id`: `br-67ebb6cf58f204c9d1b2b81b`
- `config_id`: `13-gemma4-e2b-ud-q4-k-xl`
- `case_id`: `A2-C003`
- `scope`: `results_120`
- Nivel: `A2`
- `original_has_errors` (campo auxiliar del respaldo): `true`
- `response_assessable`: `true`

**Consigna**

Explain what you do when you cannot sleep.

**Texto original del estudiante**

````text
When I cannot sleep, I get out of bed and drink a little water. I do not turn on the television because the light keeps me awake. Sometimes I read a few pages of a book until I feel tired. If I have an early class the next day, I try to go to bed sooner in the evening.
````

**Respuesta íntegra del modelo, copiada del packet**

````text
{
  "is_correct": true,
  "corrected_text": "When I cannot sleep, I get out of bed and drink a little water. I do not turn on the television because the light keeps me awake. Sometimes I read a few pages of a book until I feel tired. If I have an early class the next day, I try to go to bed sooner in the evening.",
  "errors": [],
  "feedback": "Your text is grammatically correct and perfectly understandable for an A2 level. No changes are needed."
}
````

**Registro humano vigente**

- Revisor/fecha declarados en la ficha: `kevin-01` / `2026-10-19`
- `original_has_errors`: `true`
- `response_assessable`: `true`
- Detección (`detection`): `2`
- Corrección (`correction`): `2`
- Preservación del significado (`meaning_preservation`): `2`
- Adecuación al nivel (`level_appropriateness`): `2`
- Explicación gramatical (`grammatical_explanation`): `2`
- Claridad pedagógica (`pedagogical_clarity`): `2`
- Manejo de texto correcto (`clean_text_handling`): `NA`
- `meaning_preserved`: `true`
- `explanations_ok`: `true`
- Veredicto: `CORRECT`

**Rationale íntegro**

````text
"for an A2 level" suena a un modelo repitiendo sus instrucciones. Aun así, no creo que necesariamente esté mal.
````

### 4. Conflicto de aplicabilidad indicado: Qwen4Q4 · A2-C014

- `blind_output_id`: `br-3ea9d9bb642cc426c073a910`
- `config_id`: `11-qwen35-4b-q4-k-m`
- `case_id`: `A2-C014`
- `scope`: `results_120`
- Nivel: `A2`
- `original_has_errors` (campo auxiliar del respaldo): `true`
- `response_assessable`: `true`

**Consigna**

Describe how you look after a plant or garden.

**Texto original del estudiante**

````text
There is a tomato plant on our balcony, and I water it every other day. It needs plenty of sunlight, so we move the pot when the afternoon shade reaches it. Last summer, we picked more tomatoes than we could eat. My mother made a simple sauce, and we froze the rest for later.
````

**Respuesta íntegra del modelo, copiada del packet**

````text
{
  "is_correct": true,
  "corrected_text": "There is a tomato plant on our balcony, and I water it every other day. It needs plenty of sunlight, so we move the pot when the afternoon shade reaches it. Last summer, we picked more tomatoes than we could eat. My mother made a simple sauce, and we froze the rest for later.",
  "errors": [],
  "feedback": ""
}
````

**Registro humano vigente**

- Revisor/fecha declarados en la ficha: `kevin-01` / `2026-10-19`
- `original_has_errors`: `true`
- `response_assessable`: `true`
- Detección (`detection`): `2`
- Corrección (`correction`): `2`
- Preservación del significado (`meaning_preservation`): `2`
- Adecuación al nivel (`level_appropriateness`): `2`
- Explicación gramatical (`grammatical_explanation`): `2`
- Claridad pedagógica (`pedagogical_clarity`): `2`
- Manejo de texto correcto (`clean_text_handling`): `NA`
- `meaning_preserved`: `true`
- `explanations_ok`: `true`
- Veredicto: `CORRECT`

**Rationale íntegro**

````text
OK. Feedback vacío puede ser aceptable con la respuesta correcta.
````

### 5. Conflicto de aplicabilidad indicado: GemmaUDQ4 · A2-C013

- `blind_output_id`: `br-930f5c918cb6fb7df4cc9585`
- `config_id`: `13-gemma4-e2b-ud-q4-k-xl`
- `case_id`: `A2-C013`
- `scope`: `results_120`
- Nivel: `A2`
- `original_has_errors` (campo auxiliar del respaldo): `true`
- `response_assessable`: `true`

**Consigna**

Tell a visitor how to find a place in your neighborhood.

**Texto original del estudiante**

````text
To reach the post office, walk past the bakery and turn left at the traffic lights. It is opposite the small park, next to a shop that sells newspapers. You cannot miss the bright blue door. If you get to the train station, you have gone too far, so turn around and come back one street.
````

**Respuesta íntegra del modelo, copiada del packet**

````text
```json
{
  "is_correct": true,
  "corrected_text": "To reach the post office, walk past the bakery and turn left at the traffic lights. It is opposite the small park, next to a shop that sells newspapers. You cannot miss the bright blue door. If you get to the train station, you have gone too far, so turn around and come back one street.",
  "errors": [
    {
      "original": "",
      "correction": "",
      "type": "",
      "explanation": ""
    }
  ],
  "feedback": "Your text is grammatically correct and clearly explains how to find the post office. No changes are needed."
}
```
````

**Registro humano vigente**

- Revisor/fecha declarados en la ficha: `kevin-01` / `2026-10-19`
- `original_has_errors`: `true`
- `response_assessable`: `true`
- Detección (`detection`): `0`
- Corrección (`correction`): `0`
- Preservación del significado (`meaning_preservation`): `2`
- Adecuación al nivel (`level_appropriateness`): `2`
- Explicación gramatical (`grammatical_explanation`): `0`
- Claridad pedagógica (`pedagogical_clarity`): `2`
- Manejo de texto correcto (`clean_text_handling`): `NA`
- `meaning_preserved`: `true`
- `explanations_ok`: `false`
- Veredicto: `INVALID_CASE`

**Rationale íntegro**

````text
"Turn around and come back one street" no es una expresión natural para dar direcciones; debería ser "Turn around and go back one street" o "go back to the previous street". El JSON parece marcar un error con los campos vacíos. Quizá pueda ser aceptable para A1/A2.
Posible texto corregido:
"To reach the post office, walk past the bakery and turn left at the traffic lights. It is opposite the small park, next to a shop that sells newspapers. You cannot miss the bright blue door. If you get to the train station, you have gone too far, so turn around and go back to the previous street."
````

### 6. Conflicto de aplicabilidad indicado: Qwen4Q4 · A2-C013

- `blind_output_id`: `br-f1a74afb9b236138b2f3284c`
- `config_id`: `11-qwen35-4b-q4-k-m`
- `case_id`: `A2-C013`
- `scope`: `results_120`
- Nivel: `A2`
- `original_has_errors` (campo auxiliar del respaldo): `true`
- `response_assessable`: `true`

**Consigna**

Tell a visitor how to find a place in your neighborhood.

**Texto original del estudiante**

````text
To reach the post office, walk past the bakery and turn left at the traffic lights. It is opposite the small park, next to a shop that sells newspapers. You cannot miss the bright blue door. If you get to the train station, you have gone too far, so turn around and come back one street.
````

**Respuesta íntegra del modelo, copiada del packet**

````text
{
  "is_correct": false,
  "corrected_text": "To reach the post office, walk past the bakery and turn left at the traffic lights. It is opposite the small park, next to a shop that sells newspapers. You cannot miss the bright blue door. If you get to the train station, you have gone too far, so turn around and come back one street.",
  "errors": [
    {
      "original": "come back one street",
      "correction": "come back one way",
      "type": "lexical_error",
      "explanation": "The phrase 'one street' is incorrect in this context. When giving directions, the correct expression is to say you should go back 'one way'."
    }
  ],
  "feedback": "The sentence structure is mostly clear, but 'come back one street' sounds unnatural. A more common and correct way to say this in English is 'come back one way'. Otherwise, your directions are perfect!"
}
````

**Registro humano vigente**

- Revisor/fecha declarados en la ficha: `kevin-01` / `2026-10-19`
- `original_has_errors`: `true`
- `response_assessable`: `true`
- Detección (`detection`): `1`
- Corrección (`correction`): `1`
- Preservación del significado (`meaning_preservation`): `1`
- Adecuación al nivel (`level_appropriateness`): `2`
- Explicación gramatical (`grammatical_explanation`): `0`
- Claridad pedagógica (`pedagogical_clarity`): `0`
- Manejo de texto correcto (`clean_text_handling`): `NA`
- `meaning_preserved`: `true`
- `explanations_ok`: `false`
- Veredicto: `INCORRECT`

**Rationale íntegro**

````text
"come back one street" suena poco natural, pero "come back one way" como corrección propuesta es incorrecta; sería mejor algo como "Turn around and go back one street." o "Turn around and go back to the previous street."
````

### 7. Veredicto INVALID_CASE: Qwen4Q4 · A2-C008

- `blind_output_id`: `br-275d5b7e5d4e674060fc17ca`
- `config_id`: `11-qwen35-4b-q4-k-m`
- `case_id`: `A2-C008`
- `scope`: `results_120`
- Nivel: `A2`
- `original_has_errors` (campo auxiliar del respaldo): `false`
- `response_assessable`: `true`

**Consigna**

Write about a simple way you save money.

**Texto original del estudiante**

````text
I used to buy a snack at the station every day, but I spend less now that I bring fruit from home. The change is easy, and I do not feel hungry before lunch. I put the money I save in a jar on my desk. When there is enough, I plan to buy a second-hand guitar.
````

**Respuesta íntegra del modelo, copiada del packet**

````text
{
  "is_correct": false,
  "corrected_text": "I used to buy a snack at the station every day, but I spend less now that I bring fruit from home. The change is easy, and I do not feel hungry before lunch. I put the money I save in a jar on my desk. When there is enough, I plan to buy a second-hand guitar.",
  "errors": [
    {
      "original": "The change is easy",
      "correction": "It's an easy change",
      "type": "lexical/phrasing",
      "explanation": "In this context, 'change' refers to the habit or lifestyle shift, not money. The original phrasing is awkward; 'It's an easy change' or 'The switch is easy' is more natural."
    }
  ],
  "feedback": "\"The change\" sounds unnatural here because it could be misinterpreted as \"money.\" Using \"It's an easy change\" or \"The switch is easy\" clarifies that you are talking about the lifestyle change."
}
````

**Registro humano vigente**

- Revisor/fecha declarados en la ficha: `kevin-01` / `2026-10-19`
- `original_has_errors`: `false`
- `response_assessable`: `true`
- Detección (`detection`): `NA`
- Corrección (`correction`): `NA`
- Preservación del significado (`meaning_preservation`): `2`
- Adecuación al nivel (`level_appropriateness`): `2`
- Explicación gramatical (`grammatical_explanation`): `2`
- Claridad pedagógica (`pedagogical_clarity`): `2`
- Manejo de texto correcto (`clean_text_handling`): `2`
- `meaning_preserved`: `true`
- `explanations_ok`: `true`
- Veredicto: `INVALID_CASE`

**Rationale íntegro**

````text
No es necesariamente incorrecto, especialmente para un nivel A1/A2. La recomendación que hace el modelo es válida (suena más natural). Adicionalmente, "When there is enough" podría cambiarse por "When I've saved enough", que expresa con mayor claridad que está ahorrando dinero.
````

### 8. Veredicto INVALID_CASE: Qwen4Q4 · A2-C010

- `blind_output_id`: `br-6c387cee83684e65184d3746`
- `config_id`: `11-qwen35-4b-q4-k-m`
- `case_id`: `A2-C010`
- `scope`: `results_120`
- Nivel: `A2`
- `original_has_errors` (campo auxiliar del respaldo): `false`
- `response_assessable`: `true`

**Consigna**

Compare two ways of getting around your area.

**Texto original del estudiante**

````text
Cycling to the shops takes about ten minutes, which is quicker than walking. However, the bus is more comfortable when I have heavy bags. There is a stop outside the supermarket, and the fare is not expensive. I usually choose my bike, unless it is raining or I need to carry something large.
````

**Respuesta íntegra del modelo, copiada del packet**

````text
{
  "is_correct": false,
  "corrected_text": "Cycling to the shops takes about ten minutes, which is quicker than walking. However, the bus is more comfortable when I have heavy bags. There is a stop outside the supermarket, and the fare is not expensive. I usually choose my bike unless it is raining or I need to carry something large.",
  "errors": [
    {
      "original": "I usually choose my bike",
      "correction": "I usually use my bike",
      "type": "word choice",
      "explanation": "In this context, 'use' is the standard verb for operating a vehicle or mode of transport. While 'choose' indicates selection, 'use' better fits the habitual action of riding."
    }
  ],
  "feedback": "You have correctly compared cycling and walking. To improve your natural expression, replace 'choose my bike' with 'use my bike'. This is more commonly used when talking about traveling by bicycle."
}
````

**Registro humano vigente**

- Revisor/fecha declarados en la ficha: `kevin-01` / `2026-10-19`
- `original_has_errors`: `false`
- `response_assessable`: `true`
- Detección (`detection`): `NA`
- Corrección (`correction`): `NA`
- Preservación del significado (`meaning_preservation`): `2`
- Adecuación al nivel (`level_appropriateness`): `2`
- Explicación gramatical (`grammatical_explanation`): `2`
- Claridad pedagógica (`pedagogical_clarity`): `2`
- Manejo de texto correcto (`clean_text_handling`): `2`
- `meaning_preserved`: `true`
- `explanations_ok`: `true`
- Veredicto: `INVALID_CASE`

**Rationale íntegro**

````text
"choose" enfatiza la elección, mientras que "use" enfatiza que se suele usar la bicicleta. Ambos son correctos, aunque es posible que "use" suene más natural en este contexto. La recomendación es correcta, pero no estoy seguro de que haga automáticamente la respuesta original incorrecta.
````

## Fuentes y criterio de transcripción

- Respaldo: `C:\Users\Kevin\Desktop\code\U\IA\respaldo_revision_2026-11-09T01-08-40-788Z.json`
- Packet público: `C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\analysis_v2\human_review_development60\reviewer_materials\blind_packet.json`
- Crosswalk coordinador: `C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\analysis_v2\human_review_development60\coordinator_only\identity_crosswalk.json`
- Los 8 `blind_output_id` se verificaron presentes en los tres archivos. El SHA-256 UTF-8 de cada `response_text` del packet coincide con `response_sha256` del crosswalk. Los bloques de respuesta conservan el contenido crudo, incluidas llaves, comillas y fences Markdown.
- Referencia de aplicabilidad `NA`: `SLM_A1A2/documentation/human_review_rubric_v2.md`, tabla “Anclas comunes”.

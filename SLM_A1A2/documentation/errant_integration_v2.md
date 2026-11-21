# Integración ERRANT para evaluación v2

## Propósito y alcance

La evaluación v2 usa ERRANT real para anotar el par completo de texto fuente→referencia y el par fuente→corrección del modelo. ERRANT calcula alineación lingüística con spaCy, extrae ediciones y les asigna categorías. La comparación de corrección exige la misma posición de tokens de origen y la misma cadena de corrección: `(o_start, o_end, c_str)`. El tipo ERRANT se conserva como dato descriptivo y para diagnóstico, pero no altera un TP. No hay fallback a diferencias de cadenas o a un anotador propio.

El componente está en [`scripts/gec_alignment_v2.py`](../scripts/gec_alignment_v2.py). El entorno separado vive en `.venv_eval_v2/`; no instala ni actualiza paquetes en la `.venv` principal del laboratorio. Se ejecuta únicamente en textos ya guardados. Las pruebas usan frases sintéticas; no cargan RAW del benchmark, no ejecutan modelos y no abren el test final.

ERRANT v3.0.2 está documentado para inglés y recibe idioma `en`. No se presenta como anotador español ni como adjudicador semántico. El artículo de referencia explica su alineación lingüística y su esquema de clasificación: [Bryant, Felice y Briscoe (2017), P17-1074](https://aclanthology.org/P17-1074/). El código/API y los comandos de evaluación se documentan en el [repositorio oficial de ERRANT](https://github.com/chrisjbryant/errant).

## Instalación aislada y artefactos

La máquina tenía Python 3.14.7 en la `.venv` principal, fuera del intervalo de wheels probado para esta combinación. El runtime Python 3.12.14 ya disponible en el equipo creó el entorno v2. No se instaló otro framework ni se modificó la `.venv` principal.

Desde la raíz del repositorio, en Windows x64:

```powershell
& 'C:\Users\Kevin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv SLM_A1A2/.venv_eval_v2
& SLM_A1A2/.venv_eval_v2/Scripts/python.exe -m pip install -r SLM_A1A2/requirements-evaluation-v2.txt
```

`requirements-evaluation-v2.txt` es un lock de hash completo para Windows x64/Python 3.12.14. Fija ERRANT, spaCy, `en_core_web_sm`, RapidFuzz, `click` y las dependencias resueltas; incluye un SHA-256 por cada wheel. Los wheels de Python se obtuvieron de PyPI y el modelo de la publicación oficial de spaCy en GitHub. Los reportes de instalación de pip quedan en el entorno ignorado para conservar URL y hash por distribución.

| Distribución clave | Versión | Fuente del wheel | SHA-256 |
|---|---:|---|---|
| `errant` | 3.0.2 | [PyPI](https://files.pythonhosted.org/packages/ad/af/53dca48e32428a66b6fe751b5ee0526c62c214c6b53d4a325830aac97a30/errant-3.0.2-py3-none-any.whl) | `633c03fa730822482350e6566fd199a135ff128e7d167ac404d77fcfb899019f` |
| `spacy` | 3.8.7 | [PyPI](https://files.pythonhosted.org/packages/8c/47/c17ee61b51aa8497d8af0999224b4b62485111a55ec105a06886685b2c68/spacy-3.8.7-cp312-cp312-win_amd64.whl) | `25d7a68e445200c9e9dc0044f8b7278ec0ef01ccc7cb5a95d1de2bd8e3ed6be2` |
| `en_core_web_sm` | 3.8.0 | [Publicación oficial del modelo](https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl) | `1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85` |
| `RapidFuzz` | 3.14.6 | [PyPI](https://files.pythonhosted.org/packages/84/c4/12f01df5778227c8655fcd9b429fc001d43270f5d8d154edc9066bab1de3/rapidfuzz-3.14.6-cp312-cp312-win_amd64.whl) | `cfca36e4612208875e08611a779164b6cb8900ab8bbd3d82d4cfdfae9efbfac9` |
| `click` | 8.2.1 | [PyPI](https://files.pythonhosted.org/packages/85/32/10bb5764d90a8eee674e9dc6f4db6a0ab47c8c4d0d83c27f7c39ac415a4d/click-8.2.1-py3-none-any.whl) | `61a3265b914e850b85317d0b3109c7f8cd35a670f963866005d6ef1d5175a12b` |

Se fija `click` porque la resolución actual de Typer puede omitirlo, pero spaCy importa `click` desde su CLI al inicializar. Sin ese pin, el entorno parecía instalarse bien y fallaba al importar spaCy. ERRANT se bloquea en 3.0.2; el README advierte que 2.0.0 no es compatible con Python 3.7 o posterior.

## Contrato

```python
import sys
sys.path.insert(0, "SLM_A1A2/scripts")
from gec_alignment_v2 import get_engine, score_text

engine = get_engine()
metadata = engine.metadata()
score = score_text(source, [primary_reference, complete_alternative], candidate)
```

`reference_texts[0]` siempre es la referencia primaria. Cada cadena posterior representa una referencia completa y se anota por separado desde la misma fuente. El resultado incluye:

- `primary`: TP, FP, FN, precisión, recall, F0.5, número de ediciones gold y candidatas, categorías ERRANT originales y diagnósticos de tipo para la referencia primaria.
- `best_full_reference`: el mismo registro para una única referencia completa seleccionada; `best_reference_index` y `reference_scores` conservan el índice y el resultado de todas las alternativas.
- `reference_edits` en cada resultado por referencia y `hypothesis_edits` arriba, con offsets, textos fuente/corregidos y tipo. Así se puede inspeccionar cada conteo y categoría sin reconstruir una diferencia.
- `engine_provenance`: versiones de Python, ERRANT, spaCy, `en_core_web_sm`, RapidFuzz y `click`, clase del tokenizador, componentes del pipeline y tamaño/uso de caché.

La elección de referencia se hace por caso, sobre cada referencia completa: mayor F0.5 sin redondear; empate con menor FP; después mayor TP; por último menor índice. Esta variante “mejor referencia” se informa aparte de la métrica primaria. No combina edits de alternativas ni adjudica si una alternativa significa lo mismo. Los agregados del benchmark se calculan después sumando los TP/FP/FN de cada caso según el protocolo v2.

Un candidato vacío o que no sea string se rechaza en esta API; el llamador debe omitirlo y publicar ese caso como texto no observable. Para ambos conjuntos vacíos de edits, el score de precisión, recall y F0.5 es 1.0, por convención compatible con el comparador de ERRANT; los controles se reportan como otra dimensión.

El tipo se conserva con el nombre que entrega ERRANT, por ejemplo `R:VERB:SVA`, `M:PUNCT` o `R:ORTH`. No se fuerza una taxonomía fija. `category_lineage` atribuye TP al tipo de referencia, FP al tipo de hipótesis y FN al tipo de referencia. `type_mismatches` muestra pares con edición exacta pero tipo distinto; ese diagnóstico no cambia la puntuación de corrección.

Las entradas de la API son texto crudo y se procesan con `Annotator.parse(..., tokenise=True)`, el tokenizador spaCy cargado por ERRANT. Por ello los espacios y saltos de línea finales también pueden ser edits ERRANT (`M:SPACE`/`U:SPACE`) y un espacio interno puede quedar agrupado con una edición léxica. Se preservan tal como vienen: normalizarlos cambiaría la evidencia evaluada. La prueba de integración fija esta conducta para un salto final repetible. Puntuación, contracciones, mayúsculas y tokens repetidos se prueban como ediciones observadas por ERRANT, no por reglas locales.

La caché por proceso guarda documentos spaCy y resultados de pares fuente→destino con límite de 8192 entradas. Reutiliza los edits de cada referencia y evita repetir ese análisis entre las 16 configuraciones. `metadata()` expone hits y límites para dejar rastro del estado usado al ejecutar.

## Verificación

Las fixtures sintéticas cubren sustitución exacta y equivocada, inserción, borrado, puntuación, contracción, repetición, mayúsculas, diferencias de espacios, referencias completas sin mezcla, referencia primaria frente a mejor alternativa, trazabilidad de categorías, errores de tipo y reutilización en caché.

```powershell
python SLM_A1A2/scripts/test_gec_alignment_v2.py
```

Si unittest discovery importa este módulo desde la `.venv` del laboratorio, registra una única prueba lanzadora. Esa prueba ejecuta el módulo otra vez con `SLM_A1A2/.venv_eval_v2/Scripts/python.exe`; cualquier error del proceso hijo hace fallar la lanzadora y no se convierte en un skip. El proceso hijo corre las 10 pruebas ERRANT reales y muestra su resultado. Dentro de `.venv_eval_v2`, discovery registra directamente las 10 pruebas.

Para incluirlas con el resto de las pruebas del laboratorio desde `SLM_A1A2/`:

```powershell
.venv/Scripts/python.exe -m unittest discover -s scripts -p 'test*.py'
```

# Revisión independiente — A1

**Fuente final:** `ba23982e51b7d761b2f69882d1380650fc3792688c41d6995a16379e396d6a7a`
**Instantánea inicial de esta revisión:** `6dc13fc75ffef5acf378a096b415a610ca9417fcdc9b0749cca158fe14b72c34`
**IDs revisados:** los 100 casos (`T200-A1-E001`–`T200-A1-E075`, `T200-A1-C001`–`T200-A1-C025`).

## Método
Leí y revisé lingüísticamente los 100 casos de una instantánea estable. Como el archivo cambió antes del cierre, comparé los 100 casos por ID con la fuente final y volví a revisar los dos IDs modificados: E003 y E059. No consulté salidas ni resultados de modelos.

La comprobación estructural final en Python confirmó 75 casos incorrectos con cuotas 42/20/10/3, 25 controles y 124 anotaciones. Cada sustitución reconstruye `corrected_text`; los fragmentos aparecen una vez y no se solapan. No quedaron incidencias estructurales.

## Cambios contrastados
- **E003:** el fragmento se amplió a `watched moon rise`, que identifica la construcción completa. El gold añade `the`; la alternativa con `watched the moon rising` conserva la lectura válida.
- **E059:** el texto fuente ahora dice `The guide speak softly there`; la corrección `guide speaks` cambia el verbo realmente incorrecto y las sustituciones reconstruyen el gold.
- **E027, E059 y E065:** están licenciadas las dos reparaciones de `because … so`, y el gold conserva la coma después de la cláusula inicial.
- **E070:** las alternativas `three sheets of paper` y `three pieces of paper` están licenciadas.
- **E010:** `on/onto the flat surface` queda apoyado por el contexto, que dice que el mapa se pega a la superficie. No marco la diferencia como un error de estilo.
- **E075:** el punto final de la petición cortés se acepta; no lo marco como error.

## Resultado
No quedan hallazgos abiertos en la fuente final; por eso `findings` está vacío en `A1_review_findings.json`. Revisé los 25 controles y no encontré cambios gramaticales necesarios.

**Revisor:** AI Luna6 max; no es una revisión ni aprobación humana.

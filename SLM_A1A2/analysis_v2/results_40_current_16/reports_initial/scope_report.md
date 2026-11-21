# Evaluación textual v2 — results_40_current_16

Análisis posterior de respuestas existentes. No es confirmación humana de feedback.
F0.5 es condicional al texto observable; leer su cobertura y el recall sobre todo el gold.
Ref. primaria y mejores alternativas completas se publican aparte; no hay nuevas referencias.

| Configuración | Texto observable incorrectos | P | R | F0.5 primaria | F0.5 multirref. | R todo gold | CTMR (ND) | CFAR (ND) | Esquema | JSON estricto | Flag incorrectos correcto |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|
| 01-qwen35-2b-f16 | 29/30 | 0.7288 | 0.7167 | 0.7264 | 0.7432 | 0.6719 | 3/10 (0) | 1/10 (0) | 35 | 35 | 25/30 |
| 02-qwen35-2b-q8-0 | 25/30 | 0.6852 | 0.6981 | 0.6877 | 0.7063 | 0.5781 | 3/10 (0) | 1/10 (0) | 31 | 31 | 21/30 |
| 03-qwen35-2b-q4-k-m | 28/30 | 0.5606 | 0.6491 | 0.5763 | 0.5763 | 0.5781 | 1/10 (0) | 1/10 (0) | 37 | 37 | 24/30 |
| 04-minicpm5-2b-f16 | 23/30 | 0.8333 | 0.8163 | 0.8299 | 0.8542 | 0.6250 | 0/10 (1) | 0/10 (1) | 31 | 28 | 22/30 |
| 05-minicpm5-2b-q8-0 | 25/30 | 0.8571 | 0.7925 | 0.8434 | 0.8964 | 0.6562 | 0/10 (0) | 1/10 (0) | 34 | 32 | 25/30 |
| 06-minicpm5-2b-q4-k-m | 30/30 | 0.8704 | 0.7344 | 0.8393 | 0.8393 | 0.7344 | 0/10 (0) | 0/10 (0) | 39 | 39 | 26/30 |
| 07-lfm25-12b-bf16 | 30/30 | 0.6849 | 0.7812 | 0.7022 | 0.7263 | 0.7812 | 2/10 (0) | 1/10 (0) | 40 | 40 | 3/30 |
| 08-lfm25-12b-q8-0 | 30/30 | 0.6849 | 0.7812 | 0.7022 | 0.7263 | 0.7812 | 2/10 (0) | 1/10 (0) | 40 | 40 | 3/30 |
| 09-lfm25-12b-q4-k-m | 30/30 | 0.7183 | 0.7969 | 0.7328 | 0.7571 | 0.7969 | 1/10 (0) | 0/10 (0) | 40 | 40 | 1/30 |
| 10-qwen35-4b-q8-0 | 30/30 | 0.8548 | 0.8281 | 0.8494 | 0.8494 | 0.8281 | 0/10 (0) | 0/10 (0) | 38 | 38 | 30/30 |
| 11-qwen35-4b-q4-k-m | 28/30 | 0.8621 | 0.8621 | 0.8621 | 0.8621 | 0.7812 | 0/10 (0) | 0/10 (0) | 36 | 36 | 28/30 |
| 12-gemma4-e2b-qat-q4-0 | 28/30 | 0.8548 | 0.8833 | 0.8604 | 0.8900 | 0.8281 | 0/10 (0) | 5/10 (0) | 37 | 26 | 26/30 |
| 13-gemma4-e2b-ud-q4-k-xl | 30/30 | 0.9365 | 0.9219 | 0.9335 | 0.9621 | 0.9219 | 0/10 (0) | 4/10 (0) | 37 | 6 | 28/30 |
| 14-gemma4-e2b-ud-q2-k-xl | 7/30 | 0.6500 | 0.9286 | 0.6915 | 0.6915 | 0.2031 | 1/10 (8) | 2/10 (8) | 4 | 0 | 7/30 |
| 15-lfm25-26b-q8-0 | 28/30 | 0.7500 | 0.7377 | 0.7475 | 0.7807 | 0.7031 | 0/10 (0) | 5/10 (0) | 38 | 0 | 28/30 |
| 16-lfm25-26b-q4-k-m | 28/30 | 0.7667 | 0.7667 | 0.7667 | 0.7667 | 0.7188 | 0/10 (0) | 9/10 (0) | 38 | 0 | 28/30 |

ND es no observable, no cero. CFAR usa una OR de tres valores: una alarma explícita se observa aunque el otro campo sea desconocido. Preservación completa v2 se refiere a texto/flag/lista de ediciones; el esquema se mide por separado.
Las 31 categorías intencionales y los tipos extraídos por ERRANT son taxonomías distintas. errant_categories.csv conserva la segunda sin forzar una equivalencia. Los subgrupos no se suman como observaciones independientes. Grupos de longitud sin casos no tienen rendimiento observado.
La referencia primaria contiene 64 ediciones ERRANT en los textos incorrectos esperados; la agrupación puede diferir de las anotaciones intencionales.
Las métricas originales siguen en sus carpetas intactas. El CSV configuration_summary.csv del nivel superior conserva TP/FP/FN/F0.5 originales junto a la evaluación v2 para comparar definiciones, sin confundirlas.

## Reproducción

```powershell
.\.venv_eval_v2\Scripts\python.exe scripts/report_evaluation_v2.py --scope results_40_current_16
```
Los scripts rechazan sobrescribir una entrega ya preparada. Para otro análisis, usar una versión explícita y conservar la anterior.

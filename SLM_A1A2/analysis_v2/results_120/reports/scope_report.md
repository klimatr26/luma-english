# Evaluación textual v2 — results_120

Análisis posterior de respuestas existentes. No es confirmación humana de feedback.
F0.5 es condicional al texto observable; leer su cobertura y el recall sobre todo el gold.
Ref. primaria y mejores alternativas completas se publican aparte; no hay nuevas referencias.

| Configuración | Texto observable incorrectos | P | R | F0.5 primaria | F0.5 multirref. | R todo gold | CTMR (ND) | CFAR (ND) | Esquema | JSON estricto | Flag incorrectos correcto |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|
| 01-qwen35-2b-f16 | 87/90 | 0.6067 | 0.6879 | 0.6214 | 0.6379 | 0.6626 | 3/30 (0) | 5/30 (0) | 110 | 110 | 80/90 |
| 02-qwen35-2b-q8-0 | 87/90 | 0.6111 | 0.6918 | 0.6257 | 0.6364 | 0.6748 | 3/30 (0) | 4/30 (0) | 108 | 108 | 80/90 |
| 03-qwen35-2b-q4-k-m | 89/90 | 0.6307 | 0.6894 | 0.6416 | 0.6524 | 0.6810 | 1/30 (0) | 5/30 (0) | 114 | 114 | 83/90 |
| 04-minicpm5-2b-f16 | 63/90 | 0.7570 | 0.6923 | 0.7431 | 0.7509 | 0.4969 | 2/30 (4) | 10/30 (4) | 86 | 76 | 62/90 |
| 05-minicpm5-2b-q8-0 | 67/90 | 0.8416 | 0.7456 | 0.8205 | 0.8205 | 0.5215 | 0/30 (4) | 11/30 (4) | 92 | 84 | 65/90 |
| 06-minicpm5-2b-q4-k-m | 88/90 | 0.7887 | 0.6957 | 0.7682 | 0.7866 | 0.6871 | 2/30 (0) | 3/30 (0) | 116 | 116 | 72/90 |
| 07-lfm25-12b-bf16 | 90/90 | 0.7684 | 0.8344 | 0.7807 | 0.7904 | 0.8344 | 7/30 (0) | 7/30 (0) | 118 | 118 | 3/90 |
| 08-lfm25-12b-q8-0 | 90/90 | 0.7556 | 0.8344 | 0.7701 | 0.7797 | 0.8344 | 7/30 (0) | 8/30 (0) | 118 | 118 | 2/90 |
| 09-lfm25-12b-q4-k-m | 90/90 | 0.7446 | 0.8405 | 0.7620 | 0.7705 | 0.8405 | 8/30 (0) | 1/30 (0) | 120 | 120 | 1/90 |
| 10-qwen35-4b-q8-0 | 88/90 | 0.8658 | 0.8063 | 0.8532 | 0.8707 | 0.7914 | 2/30 (0) | 4/30 (0) | 115 | 115 | 88/90 |
| 11-qwen35-4b-q4-k-m | 86/90 | 0.8366 | 0.8258 | 0.8344 | 0.8583 | 0.7853 | 2/30 (0) | 5/30 (0) | 114 | 114 | 85/90 |
| 12-gemma4-e2b-qat-q4-0 | 90/90 | 0.8773 | 0.8773 | 0.8773 | 0.8935 | 0.8773 | 0/30 (0) | 14/30 (0) | 120 | 93 | 90/90 |
| 13-gemma4-e2b-ud-q4-k-xl | 90/90 | 0.8720 | 0.8773 | 0.8730 | 0.8892 | 0.8773 | 0/30 (0) | 7/30 (0) | 116 | 19 | 88/90 |
| 14-gemma4-e2b-ud-q2-k-xl | 23/90 | 0.4189 | 0.7045 | 0.4559 | 0.4956 | 0.1902 | 6/30 (24) | 5/30 (24) | 8 | 0 | 23/90 |
| 15-lfm25-26b-q8-0 | 84/90 | 0.8657 | 0.7484 | 0.8394 | 0.8586 | 0.7117 | 0/30 (1) | 11/30 (1) | 112 | 0 | 82/90 |
| 16-lfm25-26b-q4-k-m | 85/90 | 0.8224 | 0.7911 | 0.8159 | 0.8268 | 0.7669 | 0/30 (1) | 25/30 (1) | 114 | 0 | 85/90 |

ND es no observable, no cero. CFAR usa una OR de tres valores: una alarma explícita se observa aunque el otro campo sea desconocido. Preservación completa v2 se refiere a texto/flag/lista de ediciones; el esquema se mide por separado.
Las 31 categorías intencionales y los tipos extraídos por ERRANT son taxonomías distintas. errant_categories.csv conserva la segunda sin forzar una equivalencia. Los subgrupos no se suman como observaciones independientes. Grupos de longitud sin casos no tienen rendimiento observado.
La referencia primaria contiene 163 ediciones ERRANT en los textos incorrectos esperados; la agrupación puede diferir de las anotaciones intencionales.
Las métricas originales siguen en sus carpetas intactas. El CSV configuration_summary.csv del nivel superior conserva TP/FP/FN/F0.5 originales junto a la evaluación v2 para comparar definiciones, sin confundirlas.

## Reproducción

```powershell
.\.venv_eval_v2\Scripts\python.exe scripts/report_evaluation_v2.py --scope results_120
```
Los scripts rechazan sobrescribir una entrega ya preparada. Para otro análisis, usar una versión explícita y conservar la anterior.

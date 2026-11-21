# llama.cpp readiness report — development_120

One synthetic technical probe per config (`He go to school every day.`); no benchmark content involved. Single launch attempt each; exact one generation per ready-gated config; failures recorded, never retried; -ngl never lowered.

| config | status | load_s | infer_s | toks_in/out | finish | gpu_layers | rss_peak_MiB | vram_peak_MiB(device) |
|---|---|---|---|---|---|---|---|---|
| qwen35_2b_f16 | ready | 4.6 | 1.59 | 19/132 | stop | 25/25 | 4214.6 | 4598 |
| qwen35_2b_q8_0 | ready | 2.5 | 1.47 | 19/201 | stop | 25/25 | 2432.2 | 2900 |
| qwen35_2b_q4_k_m | ready | 2.6 | 0.71 | 19/122 | stop | 25/25 | 1735.2 | 2196 |
| minicpm5_2b_f16 | ready | 2.5 | 0.61 | 20/43 | stop | 43/43 | 4832.9 | 5398 |
| minicpm5_2b_q8_0 | ready | 2.5 | 0.4 | 20/46 | stop | 43/43 | 2715.5 | 3372 |
| minicpm5_2b_q4_k_m | ready | 2.5 | 0.29 | 20/47 | stop | 43/43 | 1782.5 | 2434 |
| lfm25_12b_bf16 | ready | 2.5 | 0.38 | 16/54 | stop | 17/17 | 2657.4 | 3212 |
| lfm25_12b_q8_0 | ready | 2.6 | 0.21 | 16/48 | stop | 17/17 | 1599.5 | 2170 |
| lfm25_12b_q4_k_m | ready | 2.5 | 0.38 | 16/129 | stop | 17/17 | 1114.1 | 1678 |
| qwen35_4b_q8_0 | ready | 4.5 | 1.15 | 19/81 | stop | 33/33 | 4827.6 | 5394 |
| qwen35_4b_q4_k_m | ready | 2.5 | 0.79 | 19/75 | stop | 33/33 | 3142.5 | 3702 |
| gemma4_e2b_qat_q4_0 | ready | 2.5 | 1.0 | 16/150 | stop | 36/36 | 1914.7 | 2366 |
| gemma4_e2b_ud_q4_k_xl | ready | 2.5 | 1.17 | 16/199 | stop | 36/36 | 1760.7 | 2248 |
| gemma4_e2b_ud_q2_k_xl | ready | 2.6 | 2.74 | 16/149 | stop | 36/36 | 1441.4 | 1420 |
| lfm25_26b_q8_0 | ready | 2.5 | 0.68 | 17/79 | stop | 31/31 | 3194.4 | 3748 |
| lfm25_26b_q4_k_m | ready | 2.5 | 0.47 | 17/75 | stop | 31/31 | 2055.6 | 2604 |

## Per-config evidence (gates, errors, render)

### 01-qwen35-2b-f16 — ready
- log: `0.01.238.048 I load_tensors: offloading output layer to GPU`
- log: `0.01.238.053 I load_tensors: offloading 23 repeating layers to GPU`
- log: `0.01.238.054 I load_tensors: offloaded 25/25 layers to GPU`
- log: `0.00.135.487 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.138.724 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 95; rendered tokens: `[248045, 846, 198, 1465, 708, 310, 2812, 1396, 1834, 13, 248046, 198, 248045, 74455, 198, 248068, 271, 248069, 271]`

### 02-qwen35-2b-q8-0 — ready
- log: `0.01.113.493 I load_tensors: offloading output layer to GPU`
- log: `0.01.113.499 I load_tensors: offloading 23 repeating layers to GPU`
- log: `0.01.113.499 I load_tensors: offloaded 25/25 layers to GPU`
- log: `0.00.109.329 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.109.455 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 95; rendered tokens: `[248045, 846, 198, 1465, 708, 310, 2812, 1396, 1834, 13, 248046, 198, 248045, 74455, 198, 248068, 271, 248069, 271]`

### 03-qwen35-2b-q4-k-m — ready
- log: `0.00.993.551 I load_tensors: offloading output layer to GPU`
- log: `0.00.993.555 I load_tensors: offloading 23 repeating layers to GPU`
- log: `0.00.993.556 I load_tensors: offloaded 25/25 layers to GPU`
- log: `0.00.106.784 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.106.910 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 95; rendered tokens: `[248045, 846, 198, 1465, 708, 310, 2812, 1396, 1834, 13, 248046, 198, 248045, 74455, 198, 248068, 271, 248069, 271]`

### 04-minicpm5-2b-f16 — ready
- log: `0.00.822.094 I load_tensors: offloading output layer to GPU`
- log: `0.00.822.100 I load_tensors: offloading 41 repeating layers to GPU`
- log: `0.00.822.100 I load_tensors: offloaded 43/43 layers to GPU`
- log: `0.00.093.587 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.093.719 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 98; rendered tokens: `[0, 130072, 8448, 220, 1687, 705, 317, 2433, 1403, 1932, 35, 130073, 220, 130072, 130071, 220, 8, 130063, 9, 130063]`

### 05-minicpm5-2b-q8-0 — ready
- log: `0.00.728.680 I load_tensors: offloading output layer to GPU`
- log: `0.00.728.685 I load_tensors: offloading 41 repeating layers to GPU`
- log: `0.00.728.686 I load_tensors: offloaded 43/43 layers to GPU`
- log: `0.00.109.943 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.110.067 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 98; rendered tokens: `[0, 130072, 8448, 220, 1687, 705, 317, 2433, 1403, 1932, 35, 130073, 220, 130072, 130071, 220, 8, 130063, 9, 130063]`

### 06-minicpm5-2b-q4-k-m — ready
- log: `0.00.653.161 I load_tensors: offloading output layer to GPU`
- log: `0.00.653.166 I load_tensors: offloading 41 repeating layers to GPU`
- log: `0.00.653.167 I load_tensors: offloaded 43/43 layers to GPU`
- log: `0.00.096.930 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.097.051 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 98; rendered tokens: `[0, 130072, 8448, 220, 1687, 705, 317, 2433, 1403, 1932, 35, 130073, 220, 130072, 130071, 220, 8, 130063, 9, 130063]`

### 07-lfm25-12b-bf16 — ready
- log: `0.00.517.057 I load_tensors: offloading output layer to GPU`
- log: `0.00.517.062 I load_tensors: offloading 15 repeating layers to GPU`
- log: `0.00.517.062 I load_tensors: offloaded 17/17 layers to GPU`
- log: `0.00.114.188 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.114.308 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 76; rendered tokens: `[6, 6423, 708, 3259, 1638, 811, 2254, 1973, 2285, 523, 7, 708, 6, 64015, 708]`

### 08-lfm25-12b-q8-0 — ready
- log: `0.00.434.634 I load_tensors: offloading output layer to GPU`
- log: `0.00.434.639 I load_tensors: offloading 15 repeating layers to GPU`
- log: `0.00.434.640 I load_tensors: offloaded 17/17 layers to GPU`
- log: `0.00.095.504 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.095.618 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 76; rendered tokens: `[6, 6423, 708, 3259, 1638, 811, 2254, 1973, 2285, 523, 7, 708, 6, 64015, 708]`

### 09-lfm25-12b-q4-k-m — ready
- log: `0.00.407.414 I load_tensors: offloading output layer to GPU`
- log: `0.00.407.418 I load_tensors: offloading 15 repeating layers to GPU`
- log: `0.00.407.418 I load_tensors: offloaded 17/17 layers to GPU`
- log: `0.00.103.544 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.103.690 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 76; rendered tokens: `[6, 6423, 708, 3259, 1638, 811, 2254, 1973, 2285, 523, 7, 708, 6, 64015, 708]`

### 10-qwen35-4b-q8-0 — ready
- log: `0.01.182.345 I load_tensors: offloading output layer to GPU`
- log: `0.01.182.350 I load_tensors: offloading 31 repeating layers to GPU`
- log: `0.01.182.351 I load_tensors: offloaded 33/33 layers to GPU`
- log: `0.00.095.885 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.096.028 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 95; rendered tokens: `[248045, 846, 198, 1465, 708, 310, 2812, 1396, 1834, 13, 248046, 198, 248045, 74455, 198, 248068, 271, 248069, 271]`

### 11-qwen35-4b-q4-k-m — ready
- log: `0.01.058.855 I load_tensors: offloading output layer to GPU`
- log: `0.01.058.860 I load_tensors: offloading 31 repeating layers to GPU`
- log: `0.01.058.860 I load_tensors: offloaded 33/33 layers to GPU`
- log: `0.00.105.781 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.105.903 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 95; rendered tokens: `[248045, 846, 198, 1465, 708, 310, 2812, 1396, 1834, 13, 248046, 198, 248045, 74455, 198, 248068, 271, 248069, 271]`

### 12-gemma4-e2b-qat-q4-0 — ready
- log: `0.01.535.933 I load_tensors: offloading output layer to GPU`
- log: `0.01.535.938 I load_tensors: offloading 34 repeating layers to GPU`
- log: `0.01.535.939 I load_tensors: offloaded 36/36 layers to GPU`
- log: `0.00.094.119 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.094.242 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 59; rendered tokens: `[105, 2364, 107, 2209, 817, 531, 2528, 1418, 1719, 236761, 106, 107, 105, 4368, 107]`

### 13-gemma4-e2b-ud-q4-k-xl — ready
- log: `0.01.485.345 I load_tensors: offloading output layer to GPU`
- log: `0.01.485.350 I load_tensors: offloading 34 repeating layers to GPU`
- log: `0.01.485.350 I load_tensors: offloaded 36/36 layers to GPU`
- log: `0.00.105.978 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.106.125 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 59; rendered tokens: `[105, 2364, 107, 2209, 817, 531, 2528, 1418, 1719, 236761, 106, 107, 105, 4368, 107]`

### 14-gemma4-e2b-ud-q2-k-xl — ready
- log: `0.01.422.466 I load_tensors: offloading output layer to GPU`
- log: `0.01.422.470 I load_tensors: offloading 34 repeating layers to GPU`
- log: `0.01.422.471 I load_tensors: offloaded 36/36 layers to GPU`
- log: `0.00.094.103 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.094.226 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 59; rendered tokens: `[105, 2364, 107, 2209, 817, 531, 2528, 1418, 1719, 236761, 106, 107, 105, 4368, 107]`

### 15-lfm25-26b-q8-0 — ready
- log: `0.00.871.826 I load_tensors: offloading output layer to GPU`
- log: `0.00.871.831 I load_tensors: offloading 29 repeating layers to GPU`
- log: `0.00.871.831 I load_tensors: offloaded 31/31 layers to GPU`
- log: `0.00.094.473 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.094.596 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 83; rendered tokens: `[124899, 5922, 207, 2758, 1137, 310, 1753, 1472, 1784, 22, 124900, 207, 124899, 63514, 207, 124901]`

### 16-lfm25-26b-q4-k-m — ready
- log: `0.00.811.129 I load_tensors: offloading output layer to GPU`
- log: `0.00.811.134 I load_tensors: offloading 29 repeating layers to GPU`
- log: `0.00.811.135 I load_tensors: offloaded 31/31 layers to GPU`
- log: `0.00.105.940 I ggml_cuda_init: found 1 CUDA devices (Total VRAM: 8191 MiB):`
- log: `0.00.106.086 I load_backend: loaded CUDA backend from C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\tools\llama.cpp\b11457\ggml-cuda.dll`
- native render chars: 83; rendered tokens: `[124899, 5922, 207, 2758, 1137, 310, 1753, 1472, 1784, 22, 124900, 207, 124899, 63514, 207, 124901]`


## Current authorization and limits

16/16 pass under manifest `8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255`. This run made exactly16 synthetic requests: four expressly authorized repetitions (01–04), plus the twelve first probes (05–16). Four historical requests and their original hashes/logs remain preserved; total20. The exact repeat record is `manifests/readiness_repeat_authorization_20261011.json`, SHA `871f04d5d6fb8e4888001a18776431685d8f93eadec8cb8b3f28087dd871f66b`. Persistent exclusive claims prohibit additional generations. All16 have empty reasoning_content, nonempty content and finish_reason=stop. This checks technical readiness, not correction quality; no sampling parameters were tuned. No main benchmark or final test was executed.

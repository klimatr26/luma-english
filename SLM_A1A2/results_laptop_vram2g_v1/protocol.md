# Simulación de un presupuesto de 2 GiB de VRAM

18 de noviembre de 2026, hora de Ecuador continental. La Quadro P1000 de 4096 MiB sigue siendo el adaptador físico. Se simula el presupuesto ajustando las capas descargadas y comprobando el uso global observado contra 2048 MiB. La simulación conserva las capacidades de cómputo, ancho de banda y controlador de la Quadro.

Windows detectó corriente conectada al preparar la prueba. Se ejecuta en ese estado y con el plan de energía existente. Orden fijo: Qwen a 14/33, seguido de Gemma a 18/36. Se eligen 14 capas de Qwen porque la sonda previa de 16/33 ya observó un pico de 2053 MiB con el mismo contexto. Para Gemma se prueba la mitad. Las capas restantes se dejan en CPU. Se verifica el PCI de la Quadro y la colocación efectiva en el log.

El criterio de admisión para carga y calentamiento sintético es un pico global observado de hasta 1920 MiB, para reservar al menos 128 MiB del presupuesto simulado. Si se incumple por memoria, se prueba una variante menor en un worker limpio: Qwen 12/33 o Gemma 16/36. Un bloque de casos se interrumpe si un pico observado rebasa 2048 MiB, con registro de la fila y del fallo de presupuesto. Los picos se muestrean y pueden omitir transitorios. La VRAM incluye la actividad global del dispositivo.

Cada bloque admitido usa los mismos 15 textos de desarrollo y el mismo orden de las corridas anteriores, GGUF y DLL de b12359 verificados, puente aislado con selección de capas, contexto de 2048, máximo de 512 tokens, prompts, sampling y gramática de producción. Un worker a la vez, calentamiento fuera del conjunto, plazos de 600 s para carga y generación, RAW y registro de intentos duraderos. La comparación con CPU y con mayor descarga usa los mismos IDs y las corridas previas con corriente.

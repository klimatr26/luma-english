#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


MODELS = {
    "lfm350": {
        "repo": "LiquidAI/LFM2.5-350M",
        "q8_repo": "LiquidAI/LFM2.5-350M-GGUF",
        "q8_file": "LFM2.5-350M-Q8_0.gguf",
        "license": "LFM Open License 1.0",
    },

    "lfm12": {
        "repo": "LiquidAI/LFM2.5-1.2B-Instruct",
        "q8_repo": "LiquidAI/LFM2.5-1.2B-Instruct-GGUF",
        "q8_file": "LFM2.5-1.2B-Instruct-Q8_0.gguf",
        "license": "LFM Open License 1.0",
    },

    "lfm12think": {
        "repo": "LiquidAI/LFM2.5-1.2B-Thinking",
        "q8_repo": "LiquidAI/LFM2.5-1.2B-Thinking-GGUF",
        "q8_file": "LFM2.5-1.2B-Thinking-Q8_0.gguf",
        "license": "LFM Open License 1.0",
    },

    "qwen08": {
        "repo": "Qwen/Qwen3.5-0.8B",
        "q8_repo": "ggml-org/Qwen3.5-0.8B-GGUF",
        "q8_file": "Qwen3.5-0.8B-Q8_0.gguf",
        "license": "Apache-2.0",
    },

    "qwen2": {
        "repo": "Qwen/Qwen3.5-2B",

        # No es una cuantización oficial de Qwen.
        # Solo para las pruebas preliminares.
        "q8_repo": "bartowski/Qwen_Qwen3.5-2B-GGUF",
        "q8_file": "Qwen_Qwen3.5-2B-Q8_0.gguf",

        "license": "Apache-2.0",
    },

    "minicpm1": {
        "repo": "openbmb/MiniCPM5-1B",
        "q8_repo": "openbmb/MiniCPM5-1B-GGUF",
        "q8_file": "MiniCPM5-1B-Q8_0.gguf",
        "license": "Apache-2.0",
    },

    "minicpm2": {
        "repo": "openbmb/MiniCPM5-2B",
        "q8_repo": "openbmb/MiniCPM5-2B-GGUF",
        "q8_file": "MiniCPM5-2B-Q8_0.gguf",
        "license": "Apache-2.0",
    },

    "gemma4mobile": {
        "repo": "google/gemma-4-E2B-it-qat-mobile-transformers",
        "q8_repo": None,
        "q8_file": None,
        "license": "Apache-2.0",
    },
}

GEMMA_FULL = {
    "repo": "google/gemma-4-E2B-it",
    "q8_repo": None,
    "q8_file": None,
    "license": "Apache-2.0",
}


PACKAGES = [
    "transformers[serving]>=5.17,<6",
    "accelerate",
    "huggingface_hub[hf_xet]",
    "safetensors",
    "sentencepiece",
    "protobuf",

    # Medición
    "psutil",
    "nvidia-ml-py",
    "numpy",
    "pandas",
    "scipy",
    "scikit-learn",

    # Datasets y evaluación
    "datasets",
    "evaluate",
    "jsonschema",

    # Para la fase opcional de adaptación
    "peft",
    "trl",

    # Comparación posterior con GPT-4o
    "openai",

    # Utilidades
    "rich",
    "tqdm",
]


def run(cmd, check=True, env=None):
    print("\n>", " ".join(str(x) for x in cmd))
    return subprocess.run(
        [str(x) for x in cmd],
        check=check,
        env=env
    )


def venv_python(root):
    return root / ".venv" / "Scripts" / "python.exe"


def venv_exe(root, name):
    return root / ".venv" / "Scripts" / f"{name}.exe"


def get_hf_cmd(root):
    hf = venv_exe(root, "hf")
    if hf.exists():
        return [str(hf)]
    hf_cli = venv_exe(root, "huggingface-cli")
    if hf_cli.exists():
        return [str(hf_cli)]
    return [str(venv_python(root)), "-m", "huggingface_hub.cli.hf"]


def nvidia_available():
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        print("\nGPU detectada:")
        print(r.stdout.strip())
        return True

    except Exception:
        return False


def detect_cuda_version():
    try:
        r = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            check=True
        )
        m = re.search(r"CUDA(?:\s+UMD)?\s+Version:\s*(\d+(?:\.\d+)?)", r.stdout)
        if m:
            val = float(m.group(1))
            if val >= 13.0:
                return "13"
            elif val >= 12.0:
                return "12"
        return "12"
    except Exception:
        return None


def resolve_cuda_target(requested):
    if requested in ("13", "12", "cpu"):
        return requested
    if nvidia_available():
        ver = detect_cuda_version()
        return ver if ver else "13"
    return "cpu"


def create_environment(root, cuda_target="13"):
    print("\n=== CREANDO ENTORNO PYTHON ===")
    print(f"Versión de Python del sistema: {sys.version.split()[0]} ({sys.executable})")

    if not venv_python(root).exists():
        run([
            sys.executable,
            "-m",
            "venv",
            root / ".venv"
        ])

    py = venv_python(root)

    run([
        py,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "pip",
        "setuptools",
        "wheel"
    ])

    extra_index = None

    if cuda_target == "13":
        print("\nInstalando PyTorch con CUDA 13 (cu130)...")
        extra_index = "https://download.pytorch.org/whl/cu130"
        run([
            py,
            "-m",
            "pip",
            "install",
            "torch",
            "torchvision",
            "--index-url",
            extra_index
        ])

    elif cuda_target == "12":
        print("\nInstalando PyTorch con CUDA 12.4 (cu124)...")
        extra_index = "https://download.pytorch.org/whl/cu124"
        run([
            py,
            "-m",
            "pip",
            "install",
            "torch",
            "torchvision",
            "--index-url",
            extra_index
        ])

    else:
        print("\nNo se detectó GPU NVIDIA o se seleccionó CPU. Instalando PyTorch CPU...")
        run([
            py,
            "-m",
            "pip",
            "install",
            "torch",
            "torchvision"
        ])

    print("\nInstalando dependencias...")

    pip_cmd = [
        py,
        "-m",
        "pip",
        "install",
        *PACKAGES
    ]
    if extra_index:
        pip_cmd.extend(["--extra-index-url", extra_index])

    run(pip_cmd)

    # ERRANT y spaCy son opcionales para la fase GEC.
    print("\nInstalando herramientas GEC...")

    run([
        py,
        "-m",
        "pip",
        "install",
        "spacy",
        "errant"
    ], check=False)

    run([
        py,
        "-m",
        "spacy",
        "download",
        "en_core_web_sm"
    ], check=False)


def github_json(url):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {
        "User-Agent": "SLM-A1A2-Lab",
        "Accept": "application/vnd.github+json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        url,
        headers=headers
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as f:
            return json.load(f)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("\nError al consultar GitHub API: Límite de peticiones alcanzado (403).")
            print("Si dispone de un token de GitHub, puede definir la variable GITHUB_TOKEN.")
        raise


def download_file(url, destination):

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\nDescargando:")
    print(url)

    urllib.request.urlretrieve(
        url,
        destination
    )


def install_llama_cpp(root, cuda_target="13"):

    print("\n=== LLAMA.CPP ===")

    releases = github_json(
        "https://api.github.com/repos/"
        "ggml-org/llama.cpp/releases?per_page=25"
    )

    candidates = []
    if cuda_target == "13":
        candidates.append((
            "cuda13",
            r"bin-win-cuda-13(?:\.\d+)?-x64\.zip$",
            r"^cudart-.*bin-win-cuda-13(?:\.\d+)?-x64\.zip$"
        ))
        candidates.append((
            "cuda12",
            r"bin-win-cuda-12(?:\.\d+)?-x64\.zip$",
            r"^cudart-.*bin-win-cuda-12(?:\.\d+)?-x64\.zip$"
        ))
    elif cuda_target == "12":
        candidates.append((
            "cuda12",
            r"bin-win-cuda-12(?:\.\d+)?-x64\.zip$",
            r"^cudart-.*bin-win-cuda-12(?:\.\d+)?-x64\.zip$"
        ))
    else:
        candidates.append((
            "cpu",
            r"bin-win-cpu-x64\.zip$",
            None
        ))

    selected = None

    for flavor, main_pat, rt_pat in candidates:
        for release in releases:
            main_asset = None
            runtime_asset = None

            for asset in release.get("assets", []):
                name = asset["name"]

                if re.search(main_pat, name) and not name.startswith("cudart-"):
                    main_asset = asset

                if rt_pat and re.search(rt_pat, name):
                    runtime_asset = asset

            if main_asset and (rt_pat is None or runtime_asset is not None):
                selected = (release, main_asset, runtime_asset, flavor)
                break

        if selected is not None:
            break

    if selected is None:
        raise RuntimeError(
            "No encontré una release de llama.cpp compatible."
        )

    release, main_asset, runtime_asset, flavor = selected
    tag = release["tag_name"]
    print(f"\nSeleccionada release de llama.cpp: {tag} ({flavor})")

    target = (
        root
        / "tools"
        / "llama.cpp"
        / tag
    )

    target.mkdir(
        parents=True,
        exist_ok=True
    )

    assets = [main_asset]

    if runtime_asset:
        assets.append(runtime_asset)

    for asset in assets:

        zip_path = (
            root
            / "tools"
            / asset["name"]
        )

        if not zip_path.exists():
            download_file(
                asset["browser_download_url"],
                zip_path
            )

        print(
            "Extrayendo",
            zip_path.name
        )

        with zipfile.ZipFile(
            zip_path
        ) as archive:

            archive.extractall(
                target
            )

    servers = list(
        target.rglob(
            "llama-server.exe"
        )
    )

    if not servers:
        raise RuntimeError(
            "No apareció llama-server.exe."
        )

    print(
        "\nllama.cpp instalado:",
        tag
    )

    print(
        "Servidor:",
        servers[0]
    )

    return str(servers[0])


def hf_environment(root):

    env = os.environ.copy()

    env["HF_HOME"] = str(
        root / "hf_cache"
    )

    # Xet se usa actualmente para archivos grandes de HF.
    env["HF_XET_HIGH_PERFORMANCE"] = "1"

    return env


def download_full_models(root, selected):

    print("\n=== MODELOS TRANSFORMERS ===")

    hf_cmd = get_hf_cmd(root)
    env = hf_environment(root)

    for alias, info in selected.items():

        repo = info["repo"]

        print(
            "\n",
            alias,
            "->",
            repo
        )

        run([
            *hf_cmd,
            "download",
            repo,
            "--cache-dir",
            root / "hf_cache"
        ], env=env)


def download_q8_models(root, selected):

    print("\n=== MODELOS GGUF Q8_0 ===")

    hf_cmd = get_hf_cmd(root)
    env = hf_environment(root)

    for alias, info in selected.items():

        repo = info.get(
            "q8_repo"
        )

        filename = info.get(
            "q8_file"
        )

        if not repo or not filename:
            print(
                f"\n{alias}: "
                "no hay Q8 configurado; "
                "se omite."
            )
            continue

        destination = (
            root
            / "models"
            / "gguf"
            / alias
        )

        destination.mkdir(
            parents=True,
            exist_ok=True
        )

        print(
            "\n",
            alias,
            repo,
            filename
        )

        run([
            *hf_cmd,
            "download",
            repo,
            filename,
            "--local-dir",
            destination
        ], env=env)


def create_launchers(root, llama_server):

    launchers = (
        root
        / "launchers"
    )

    launchers.mkdir(
        parents=True,
        exist_ok=True
    )

    activate = launchers / "activate_lab.bat"

    activate.write_text(
        "@echo off\n"
        f'set "HF_HOME={root / "hf_cache"}"\n'
        'set "HF_XET_HIGH_PERFORMANCE=1"\n'
        f'call "{root / ".venv" / "Scripts" / "activate.bat"}"\n',
        encoding="utf-8"
    )

    transformers_server = (
        launchers
        / "start_transformers_server.bat"
    )

    tf_exe = venv_exe(root, "transformers")
    tf_cmd_str = f'"{tf_exe}"' if tf_exe.exists() else f'"{venv_python(root)}" -m transformers.cli.transformers'

    transformers_server.write_text(
        "@echo off\n"
        f'set "HF_HOME={root / "hf_cache"}"\n'
        'set "HF_XET_HIGH_PERFORMANCE=1"\n'
        f'{tf_cmd_str} '
        "serve --model-timeout -1\n",
        encoding="utf-8"
    )

    diagnostic = (
        launchers
        / "diagnose.bat"
    )

    py = venv_python(root)

    diagnostic.write_text(
        "@echo off\n"
        f'"{py}" -c "'
        "import torch,transformers;"
        "print('torch:',torch.__version__);"
        "print('transformers:',transformers.__version__);"
        "print('CUDA:',torch.cuda.is_available());"
        "print('GPU:',torch.cuda.get_device_name(0) "
        "if torch.cuda.is_available() else 'CPU');"
        "print('BF16:',torch.cuda.is_bf16_supported() "
        "if torch.cuda.is_available() else False)"
        '"\n'
        "nvidia-smi\n"
        "pause\n",
        encoding="utf-8"
    )

    if llama_server:

        for alias in MODELS:

            model_dir = (
                root
                / "models"
                / "gguf"
                / alias
            )

            if not model_dir.exists():
                continue

            ggufs = list(
                model_dir.glob(
                    "*.gguf"
                )
            )

            for gguf in ggufs:

                bat = (
                    launchers
                    / f"serve_{alias}_q8.bat"
                )

                bat.write_text(
                    "@echo off\n"
                    f'"{llama_server}" '
                    f'-m "{gguf}" '
                    "-c 4096 "
                    "-ngl 999 "
                    "--host 127.0.0.1 "
                    "--port 8080\n",
                    encoding="utf-8"
                )


def select_models(value):

    if value == "all":
        return dict(MODELS)

    aliases = [
        x.strip()
        for x in value.split(",")
        if x.strip()
    ]

    result = {}

    for alias in aliases:

        if alias not in MODELS:

            raise SystemExit(
                f"Modelo desconocido: {alias}"
            )

        result[alias] = MODELS[alias]

    return result


def main():

    if os.name != "nt":

        raise SystemExit(
            "Este script está preparado para Windows."
        )

    parser = argparse.ArgumentParser(
        description="Configuración del laboratorio local de SLM en Windows"
    )

    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd()
        / "SLM_A1A2_Lab"
    )

    parser.add_argument(
        "--install",
        action="store_true",
        help="Crear entorno virtual e instalar dependencias Python"
    )

    parser.add_argument(
        "--llamacpp",
        action="store_true",
        help="Descargar y configurar binarios de llama.cpp"
    )

    parser.add_argument(
        "--download-full",
        action="store_true",
        help="Descargar modelos completos (Transformers / Safetensors)"
    )

    parser.add_argument(
        "--download-q8",
        action="store_true",
        help="Descargar modelos cuantizados GGUF Q8_0"
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Ejecutar todo: entorno, llama.cpp y descarga de modelos"
    )

    parser.add_argument(
        "--cuda",
        choices=["auto", "13", "12", "cpu"],
        default="auto",
        help="Objetivo CUDA para PyTorch y llama.cpp (auto, 13, 12, cpu)"
    )

    parser.add_argument(
        "--models",
        default="all",
        help="Modelos a descargar (separados por coma o 'all')"
    )

    parser.add_argument(
        "--include-gemma-full",
        action="store_true",
        help="Incluir modelo completo no cuantizado Gemma 4 E2B"
    )

    args = parser.parse_args()

    # Si no se pasó ninguna acción específica, asumir --all para preparar y descargar todo
    if not (args.install or args.llamacpp or args.download_full or args.download_q8 or args.all):
        print("\nNo se especificaron acciones individuales; se asume '--all' para preparar el entorno y descargar modelos.")
        args.all = True

    if args.all:

        args.install = True
        args.llamacpp = True
        args.download_full = True
        args.download_q8 = True

    cuda_target = resolve_cuda_target(args.cuda)
    print(f"\nObjetivo de aceleración seleccionado: {cuda_target.upper()}")

    root = args.root.resolve()

    root.mkdir(
        parents=True,
        exist_ok=True
    )

    print(
        "\nLaboratorio:",
        root
    )

    free = (
        shutil.disk_usage(root).free
        / 1024**3
    )

    print(
        f"Espacio libre: {free:.1f} GiB"
    )

    if args.all and free < 45:

        print(
            "\nADVERTENCIA: "
            "recomiendo al menos ~45 GiB libres."
        )

    if args.install:
        create_environment(root, cuda_target=cuda_target)

    llama_server = None

    if args.llamacpp:
        llama_server = install_llama_cpp(root, cuda_target=cuda_target)

    selected = select_models(
        args.models
    )

    if args.include_gemma_full:

        selected["gemma4full"] = (
            GEMMA_FULL
        )

    if args.download_full:

        download_full_models(
            root,
            selected
        )

    if args.download_q8:

        download_q8_models(
            root,
            selected
        )

    # Si llama.cpp se instaló en una ejecución anterior,
    # tratar de localizarlo.
    if llama_server is None:

        possible = list(
            (
                root
                / "tools"
                / "llama.cpp"
            ).rglob(
                "llama-server.exe"
            )
        )

        if possible:
            llama_server = str(
                possible[0]
            )

    create_launchers(
        root,
        llama_server
    )

    print(
        "\nPreparación terminada."
    )

    print(
        "\nEjecute:"
    )

    print(
        root
        / "launchers"
        / "diagnose.bat"
    )


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""Prepare one pinned Qwen 3.5 4B GGUF for the writing demo.

This is an explicit, user-triggered helper. It downloads only the pinned text
checkpoint and tokenizer/configuration files, then uses the project's local
llama.cpp b11457 converter and quantizer. It never installs runtimes or
replaces existing files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


MODEL_REPO = "Qwen/Qwen3.5-4B"
MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
LLAMA_COMMIT = "5ad1c5da0ad7f6176256b823925aad19134f0263"
CONVERTER_SHA256 = "e9a1da876330bbce9687541ab31736542a01b4ac43c6686126514a50f122fb7f"
SOURCE_WEIGHT_FILES = (
    "model.safetensors-00001-of-00002.safetensors",
    "model.safetensors-00002-of-00002.safetensors",
)
SOURCE_FILES = (
    "LICENSE",
    "chat_template.jinja",
    "config.json",
    "merges.txt",
    "model.safetensors.index.json",
    "model.safetensors-00001-of-00002.safetensors",
    "model.safetensors-00002-of-00002.safetensors",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)


class PreparationError(RuntimeError):
    pass


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep bearer credentials on their original HTTPS authority only."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        old = urlsplit(request.full_url)
        new = urlsplit(new_url)
        if old.scheme.lower() == "https" and new.scheme.lower() != "https":
            raise PreparationError("Se rechazó una redirección HTTPS a HTTP durante la descarga de una fuente.")

        redirected = super().redirect_request(request, file_pointer, code, message, headers, new_url)
        if redirected is not None and old.netloc.casefold() != new.netloc.casefold():
            redirected.remove_header("Authorization")
            redirected.remove_header("Proxy-Authorization")
        return redirected


SAFE_OPENER = urllib.request.build_opener(SafeRedirectHandler())


def print_progress(message: str) -> None:
    print(message, flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    size = path.stat().st_size
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def is_gguf(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(4) == b"GGUF"
    except OSError:
        return False


def verify_artifact(path: Path, expected_size: int, expected_sha256: str, *, label: str) -> None:
    if not path.is_file():
        raise PreparationError(f"Falta {label}: {path}")
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise PreparationError(
            f"Tamaño incorrecto para {label}: {actual_size} bytes; se esperaban {expected_size}. "
            f"Se conserva el archivo en {path}."
        )
    if not is_gguf(path):
        raise PreparationError(f"La cabecera de {label} no es GGUF. Se conserva el archivo en {path}.")
    actual_hash = sha256_file(path)
    if actual_hash.lower() != expected_sha256.lower():
        raise PreparationError(
            f"SHA-256 incorrecto para {label}: {actual_hash}; se esperaba {expected_sha256}. "
            f"Se conserva el archivo en {path}."
        )


def publish_no_replace(partial: Path, destination: Path) -> None:
    """Publish an already-verified same-volume file with an atomic no-overwrite link."""
    try:
        os.link(partial, destination)
    except FileExistsError as error:
        raise PreparationError(f"Ya existe {destination}; no se reemplazó.") from error
    except OSError as error:
        raise PreparationError(
            f"No se pudo publicar {destination} sin reemplazarlo. "
            f"El archivo temporal verificado permanece en {partial}: {error}"
        ) from error
    partial.unlink()


def parse_marker(marker: Path) -> tuple[str, str] | None:
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None
    return lines[0].strip(), lines[1].strip()


def validate_source_file(path: Path, filename: str, expected_sha256: str | None) -> None:
    marker = path.parent / ".cache" / "huggingface" / "download" / f"{filename}.metadata"
    parsed = parse_marker(marker)
    if parsed is None or parsed[0] != MODEL_REVISION:
        raise PreparationError(
            f"El archivo fuente existente no tiene una marca de revisión {MODEL_REVISION}: {path}. "
            "Se conserva sin reemplazarlo."
        )
    if not path.is_file() or path.stat().st_size == 0:
        raise PreparationError(f"El archivo fuente está vacío o no existe: {path}.")

    recorded_hash = parsed[1]
    if recorded_hash.startswith("local-sha256:"):
        actual = sha256_file(path)
        expected_local = recorded_hash.removeprefix("local-sha256:")
        if actual.lower() != expected_local.lower():
            raise PreparationError(f"El archivo fuente cambió después de descargarse: {path}.")
    elif re.fullmatch(r"[0-9a-fA-F]{64}", recorded_hash):
        if sha256_file(path).lower() != recorded_hash.lower():
            raise PreparationError(f"El archivo fuente no coincide con los metadatos fijados: {path}.")
    elif re.fullmatch(r"[0-9a-fA-F]{40}", recorded_hash):
        if git_blob_sha1(path).lower() != recorded_hash.lower():
            raise PreparationError(f"El archivo fuente no coincide con los metadatos fijados: {path}.")
    else:
        raise PreparationError(f"Los metadatos no tienen un hash reconocible para {path}; no se usará el archivo.")

    if expected_sha256 is not None:
        actual_weight_hash = sha256_file(path)
        if actual_weight_hash.lower() != expected_sha256.lower():
            raise PreparationError(
                f"El peso {filename} no coincide con SHA-256 esperado del inventario: {actual_weight_hash}. "
                "Se conserva sin reemplazarlo."
            )


def source_hashes_from_inventory(inventory: dict[str, Any]) -> dict[str, str]:
    entries = inventory.get("roots", [])
    inventory_entries = [entry for root in entries for entry in root.get("entries", [])]
    hashes: dict[str, str] = {}
    for filename in SOURCE_WEIGHT_FILES:
        matches = [
            item for item in inventory_entries
            if item.get("file") == filename and item.get("hf_commit") == MODEL_REVISION
        ]
        if len(matches) != 1:
            raise PreparationError(f"El inventario no identifica de forma única el peso fuente {filename}.")
        expected = matches[0].get("lfs_sha256_expected") or matches[0].get("sha256")
        if not expected or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            raise PreparationError(f"El inventario no contiene un SHA-256 válido para {filename}.")
        hashes[filename] = expected.lower()
    return hashes


def write_marker_no_replace(marker: Path, value: str) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_name(marker.name + f".partial-{uuid.uuid4().hex}")
    temporary.write_text(value + "\n", encoding="utf-8", newline="\n")
    publish_no_replace(temporary, marker)


def download_source_file(source_dir: Path, filename: str, expected_sha256: str | None) -> None:
    destination = source_dir / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + f".partial-{uuid.uuid4().hex}")
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in filename.split("/"))
    url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{encoded_path}?download=true"
    headers = {"User-Agent": "WritingDemo/1.0 pinned Qwen source preparation"}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)

    print_progress(f"Descargando fuente fijada: {filename}")
    try:
        with SAFE_OPENER.open(request, timeout=60) as response, partial.open("xb") as output:
            total = response.headers.get("Content-Length")
            total_bytes = int(total) if total and total.isdigit() else None
            received = 0
            last_report = 0
            while chunk := response.read(4 * 1024 * 1024):
                output.write(chunk)
                received += len(chunk)
                if received - last_report >= 32 * 1024 * 1024:
                    denominator = f"/{total_bytes} bytes" if total_bytes is not None else " bytes"
                    print_progress(f"  {filename}: {received}{denominator}")
                    last_report = received
            output.flush()
            os.fsync(output.fileno())
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 429:
            raise PreparationError(
                f"Hugging Face respondió HTTP 429 al descargar {filename}. "
                "La operación se detuvo sin reintentos; espera antes de volver a intentarlo."
            ) from error
        raise PreparationError(f"Hugging Face respondió HTTP {error.code} para {filename}.") from error
    except urllib.error.URLError as error:
        raise PreparationError(f"No se pudo descargar {filename} desde su revisión fijada: {error.reason}.") from error

    if partial.stat().st_size == 0:
        raise PreparationError(f"Hugging Face entregó un archivo vacío para {filename}; queda en {partial}.")
    actual_sha = sha256_file(partial)
    if expected_sha256 is not None and actual_sha.lower() != expected_sha256.lower():
        raise PreparationError(
            f"El peso descargado {filename} no coincide con el SHA-256 del inventario: {actual_sha}. "
            f"Se conserva en {partial}."
        )

    publish_no_replace(partial, destination)
    write_marker_no_replace(
        source_dir / ".cache" / "huggingface" / "download" / f"{filename}.metadata",
        f"{MODEL_REVISION}\nlocal-sha256:{actual_sha}",
    )
    print_progress(f"Fuente lista: {filename}")


def ensure_source_snapshot(models_dir: Path, inventory: dict[str, Any]) -> Path:
    # Read the large input hashes from the checked-in inventory before any network access.
    source_hashes = source_hashes_from_inventory(inventory)

    source_dir = models_dir / "qwen35_4b" / "source_hf"
    for filename in SOURCE_FILES:
        path = source_dir / filename
        expected_sha = source_hashes.get(filename)
        if path.exists():
            validate_source_file(path, filename, expected_sha)
            continue
        download_source_file(source_dir, filename, expected_sha)
        validate_source_file(path, filename, expected_sha)
    return source_dir


def run_command(command: list[str], *, cwd: Path, title: str) -> None:
    print_progress(title)
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as error:
        raise PreparationError(f"No se pudo iniciar la herramienta local para {title}: {error}.") from error
    assert process.stdout is not None
    for line in process.stdout:
        text = line.rstrip()
        if text:
            print_progress(f"  {text}")
    return_code = process.wait()
    if return_code != 0:
        raise PreparationError(f"La herramienta local falló durante {title} (código {return_code}).")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreparationError(f"No se pudo leer el manifiesto {path}: {error}.") from error


def locate_config(manifest: dict[str, Any], config_id: str) -> dict[str, Any]:
    for item in manifest.get("configurations", []):
        if item.get("id") == config_id:
            return item
    raise PreparationError(f"No aparece la configuración {config_id} en experiment_manifest_120.json.")


def verify_existing_or_absent(path: Path, expected_size: int, expected_sha: str, *, label: str) -> bool:
    if not path.exists():
        return False
    verify_artifact(path, expected_size, expected_sha, label=label)
    return True


def required_runtime_files(lab_dir: Path, conversion_record: dict[str, Any]) -> tuple[Path, Path, Path]:
    python = lab_dir / ".venv" / "Scripts" / "python.exe"
    converter = lab_dir / "tools" / "llama.cpp" / f"llama.cpp-{LLAMA_COMMIT}" / "convert_hf_to_gguf.py"
    quantizer = lab_dir / "tools" / "llama.cpp" / "b11457" / "llama-quantize.exe"
    for path, name in ((python, "Python del entorno .venv"), (converter, "convert_hf_to_gguf.py fijado"), (quantizer, "llama-quantize.exe b11457")):
        if not path.is_file():
            raise PreparationError(
                f"Falta {name}: {path}. Configura localmente el runtime requerido; este helper no descarga ni instala herramientas."
            )
    actual_converter_hash = sha256_file(converter)
    expected_converter_hash = conversion_record.get("converter_sha256", CONVERTER_SHA256)
    if actual_converter_hash.lower() != CONVERTER_SHA256.lower() or expected_converter_hash.lower() != CONVERTER_SHA256.lower():
        raise PreparationError("El conversor local no coincide con el hash fijado en qwen_conversion_record_120.json.")
    qwen_module = converter.parent / "conversion" / "qwen.py"
    if not qwen_module.is_file() or "Qwen3_5ForConditionalGeneration" not in qwen_module.read_text(encoding="utf-8", errors="replace"):
        raise PreparationError("El conversor fijado no registra soporte para Qwen3.5; se detuvo sin sustituirlo.")
    return python, converter, quantizer


def run(args: argparse.Namespace) -> Path:
    script_path = Path(__file__).resolve()
    lab_dir = script_path.parents[2]
    models_dir = Path(args.models_dir).expanduser().resolve()
    if not models_dir.is_dir():
        raise PreparationError(f"La carpeta de modelos no existe: {models_dir}")

    manifest_path = lab_dir / "manifests" / "experiment_manifest_120.json"
    inventory_path = lab_dir / "manifests" / "model_inventory_120.json"
    conversion_record_path = lab_dir / "manifests" / "qwen_conversion_record_120.json"
    manifest = read_json(manifest_path)
    inventory = read_json(inventory_path)
    conversion_record = read_json(conversion_record_path)

    model = locate_config(manifest, f"qwen35_4b_{'q8_0' if args.quant == 'Q8_0' else 'q4_k_m'}")
    expected_size = int(model["gguf"]["bytes"])
    expected_sha = str(model["model_sha256"])
    output_name = f"Qwen3.5-4B-{args.quant}.gguf"
    output_dir = models_dir / "qwen_converted"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name

    if verify_existing_or_absent(output_path, expected_size, expected_sha, label=f"Qwen 3.5 4B {args.quant}"):
        print_progress(f"El GGUF verificado ya existe; no se convirtió de nuevo: {output_path}")
        return output_path

    python, converter, quantizer = required_runtime_files(lab_dir, conversion_record)
    source_dir = ensure_source_snapshot(models_dir, inventory)

    f16_record = next(
        (item for item in conversion_record.get("outputs", [])
         if item.get("model") == "Qwen3.5-4B" and item.get("quant") == "F16"),
        None,
    )
    if f16_record is None:
        raise PreparationError("qwen_conversion_record_120.json no contiene el intermedio Qwen 4B F16.")
    f16_path = output_dir / "Qwen3.5-4B-F16.gguf"
    f16_size = int(f16_record["bytes"])
    f16_sha = str(f16_record["sha256"])
    if not verify_existing_or_absent(f16_path, f16_size, f16_sha, label="intermedio Qwen 3.5 4B F16"):
        partial_f16 = output_dir / f"Qwen3.5-4B-F16.partial-{uuid.uuid4().hex}.gguf"
        run_command(
            [str(python), str(converter), str(source_dir), "--outfile", str(partial_f16), "--outtype", "f16", "--no-nextn"],
            cwd=lab_dir,
            title="Convirtiendo el checkpoint fijado a GGUF F16 de texto",
        )
        verify_artifact(partial_f16, f16_size, f16_sha, label="conversión temporal Qwen 4B F16")
        publish_no_replace(partial_f16, f16_path)
        print_progress(f"Intermedio F16 verificado: {f16_path}")

    partial_output = output_dir / f"Qwen3.5-4B-{args.quant}.partial-{uuid.uuid4().hex}.gguf"
    run_command(
        [str(quantizer), str(f16_path), str(partial_output), args.quant],
        cwd=lab_dir,
        title=f"Cuantizando Qwen 3.5 4B a {args.quant}",
    )
    verify_artifact(partial_output, expected_size, expected_sha, label=f"conversión temporal Qwen 4B {args.quant}")
    publish_no_replace(partial_output, output_path)
    print_progress(f"GGUF Qwen 3.5 4B verificado: {output_path}")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", required=True, help="Carpeta de modelos que contiene qwen35_4b y qwen_converted")
    parser.add_argument("--quant", required=True, choices=("Q8_0", "Q4_K_M"), help="Cuantización que se generará")
    args = parser.parse_args()
    try:
        run(args)
        return 0
    except PreparationError as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("ERROR: preparación cancelada; se conservan los archivos parciales propios.", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

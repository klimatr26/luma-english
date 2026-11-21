#Requires -Version 5.1
# Config 13/16 dev-120: 13-gemma4-e2b-ud-q4-k-xl [UD-Q4_K_XL] Unsloth Dynamic non-uniform, not Q4_K_M
# Native GGUF template (no --chat-template/--chat-template-file), no mmproj/MTP/speculative/grammar.
# Foreground process: Ctrl+C stops cleanly. Source of truth: manifests/experiment_manifest_120.json.
param([int]$Port = 8113)
$ErrorActionPreference = 'Stop'
$Lab = Split-Path $PSScriptRoot -Parent
$Server = Join-Path $Lab 'tools\llama.cpp\b11457\llama-server.exe'
$Model = Join-Path $Lab 'models/gemma4_e2b/unsloth_dynamic/gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf'
if (!(Test-Path $Server)) { Write-Error "missing server: $Server"; exit 1 }
if (!(Test-Path $Model)) { Write-Error "missing model: $Model"; exit 1 }
$LogDir = Join-Path $Lab 'logs\servers'; New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'gemma4_e2b_ud_q4_k_xl.log'
& $Server -m $Model --host 127.0.0.1 --port $Port -c 4096 --parallel 1 -lv 4 -ngl 999 -s 42 --reasoning off --reasoning-budget 0 --log-file $Log --chat-template-kwargs '{"enable_thinking":false}'

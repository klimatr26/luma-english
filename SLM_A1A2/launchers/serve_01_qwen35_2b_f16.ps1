#Requires -Version 5.1
# Config 01/16 dev-120: 01-qwen35-2b-f16 [F16] converted reference (PRESENT_UNVERIFIED: run conversion recipe first)
# Native GGUF template (no --chat-template/--chat-template-file), no mmproj/MTP/speculative/grammar.
# Foreground process: Ctrl+C stops cleanly. Source of truth: manifests/experiment_manifest_120.json.
param([int]$Port = 8101)
$ErrorActionPreference = 'Stop'
$Lab = Split-Path $PSScriptRoot -Parent
$Server = Join-Path $Lab 'tools\llama.cpp\b11457\llama-server.exe'
$Model = 'D:/SLM_A1A2_models/qwen_converted/Qwen3.5-2B-F16.gguf'
if (!(Test-Path $Server)) { Write-Error "missing server: $Server"; exit 1 }
if (!(Test-Path $Model)) { Write-Error "missing model: $Model"; exit 1 }
$LogDir = Join-Path $Lab 'logs\servers'; New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'qwen35_2b_f16.log'
& $Server -m $Model --host 127.0.0.1 --port $Port -c 4096 --parallel 1 -lv 4 -ngl 999 -s 42 --reasoning off --reasoning-budget 0 --log-file $Log --chat-template-kwargs '{"enable_thinking":false}'

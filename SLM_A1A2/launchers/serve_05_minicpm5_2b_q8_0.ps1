#Requires -Version 5.1
# Config 05/16 dev-120: 05-minicpm5-2b-q8-0 [Q8_0] high-fidelity PTQ anchor
# Native GGUF template (no --chat-template/--chat-template-file), no mmproj/MTP/speculative/grammar.
# Foreground process: Ctrl+C stops cleanly. Source of truth: manifests/experiment_manifest_120.json.
param([int]$Port = 8105)
$ErrorActionPreference = 'Stop'
$Lab = Split-Path $PSScriptRoot -Parent
$Server = Join-Path $Lab 'tools\llama.cpp\b11457\llama-server.exe'
$Model = Join-Path $Lab 'models/minicpm5_2b/MiniCPM5-2B-Q8_0.gguf'
if (!(Test-Path $Server)) { Write-Error "missing server: $Server"; exit 1 }
if (!(Test-Path $Model)) { Write-Error "missing model: $Model"; exit 1 }
$LogDir = Join-Path $Lab 'logs\servers'; New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'minicpm5_2b_q8_0.log'
& $Server -m $Model --host 127.0.0.1 --port $Port -c 4096 --parallel 1 -lv 4 -ngl 999 -s 42 --reasoning off --reasoning-budget 0 --log-file $Log --chat-template-kwargs '{"enable_thinking":false}'

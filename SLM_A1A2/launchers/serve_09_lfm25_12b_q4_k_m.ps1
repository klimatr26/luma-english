#Requires -Version 5.1
# Config 09/16 dev-120: 09-lfm25-12b-q4-k-m [Q4_K_M] balanced K-quant; distinct from QAD-Q4_0
# Native GGUF template (no --chat-template/--chat-template-file), no mmproj/MTP/speculative/grammar.
# Foreground process: Ctrl+C stops cleanly. Source of truth: manifests/experiment_manifest_120.json.
param([int]$Port = 8109)
$ErrorActionPreference = 'Stop'
$Lab = Split-Path $PSScriptRoot -Parent
$Server = Join-Path $Lab 'tools\llama.cpp\b11457\llama-server.exe'
$Model = Join-Path $Lab 'models/lfm25_12b/LFM2.5-1.2B-Instruct-Q4_K_M.gguf'
if (!(Test-Path $Server)) { Write-Error "missing server: $Server"; exit 1 }
if (!(Test-Path $Model)) { Write-Error "missing model: $Model"; exit 1 }
$LogDir = Join-Path $Lab 'logs\servers'; New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'lfm25_12b_q4_k_m.log'
& $Server -m $Model --host 127.0.0.1 --port $Port -c 4096 --parallel 1 -lv 4 -ngl 999 -s 42 --reasoning off --reasoning-budget 0 --log-file $Log

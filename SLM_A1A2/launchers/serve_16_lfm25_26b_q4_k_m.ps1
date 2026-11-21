#Requires -Version 5.1
# Config 16-lfm25-26b-q4-k-m: Q4_K_M; native template; synthetic readiness only before approval.
param([int]$Port = 8116)
$ErrorActionPreference = 'Stop'
$Lab = Split-Path $PSScriptRoot -Parent
$Server = Join-Path $Lab 'tools\llama.cpp\b11457\llama-server.exe'
$Model = Join-Path $Lab 'models/lfm25_26b/LFM2.5-2.6B-Q4_K_M.gguf'
if (!(Test-Path -LiteralPath $Server)) { throw 'Missing server' }
if (!(Test-Path -LiteralPath $Model)) { throw 'Missing pinned model' }
$LogDir = Join-Path $Lab 'logs\servers'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'lfm25_26b_q4_k_m.log'
& $Server -m $Model --host 127.0.0.1 --port $Port -c 4096 --parallel 1 -lv 4 -ngl 999 -s 42 --reasoning off --reasoning-budget 0 --log-file $Log

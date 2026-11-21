#Requires -Version 5.1
<#
.SYNOPSIS
  Reproducible Qwen3.5 -> GGUF conversion + quantization for Phase 2 (dev-120).
.DESCRIPTION
  Preflight (read-only) runs by default. Heavy steps (convert/quantize) run
  ONLY with -Execute. Never downloads weights: sources are the pinned local
  checkpoints. Never runs inference. The main agent reviews preflight output
  and this script before passing -Execute.

  Pinned inputs:
    Qwen3.5-2B source  Qwen/Qwen3.5-2B  rev 15852e8c16360a2fea060d615a32b45270f8a8fc (Apache-2.0)
    Qwen3.5-4B source  Qwen/Qwen3.5-4B  rev 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a (Apache-2.0)
    llama.cpp b11457, commit 5ad1c5da0 (llama-server --version 0.6.0-dev build 11457)
  Outputs (2B): <out>/Qwen3.5-2B-F16.gguf, -Q8_0.gguf, -Q4_K_M.gguf
  Outputs (4B): <out>/Qwen3.5-4B-Q8_0.gguf, -Q4_K_M.gguf (F16 kept as intermediate only)
  Record: manifests/qwen_conversion_record_120.json (params, hashes, sizes)

  Requirements resolved at review time by the main agent:
    -ConverterScript: convert_hf_to_gguf.py from llama.cpp @ 5ad1c5da0
     (bin ZIPs do not ship it; .venv has NO gguf package yet).
    The script STOPS unless the converter registers qwen3_5 support.
.PARAMETER Model
  '2B' and/or '4B' (default both).
.PARAMETER ConverterScript
  Full path to convert_hf_to_gguf.py @ commit 5ad1c5da0.
.PARAMETER OutDir
  Output dir for GGUFs (default D:\SLM_A1A2_models\qwen_converted).
.PARAMETER Execute
  Required to run convert/quantize. Without it: preflight only.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\build_qwen_gguf_b11457.ps1 -Model 2B
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\build_qwen_gguf_b11457.ps1 -Model 2B,4B -ConverterScript D:\tools\convert_hf_to_gguf.py -Execute
#>
param(
  [ValidateSet('2B', '4B')]
  [string[]]$Model = @('2B', '4B'),
  [string]$ConverterScript = '',
  [string]$OutDir = 'D:\SLM_A1A2_models\qwen_converted',
  [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$Lab = Split-Path $PSScriptRoot -Parent
$Bin = Join-Path $Lab 'tools\llama.cpp\b11457'
$Quantize = Join-Path $Bin 'llama-quantize.exe'
$VenvPy = Join-Path $Lab '.venv\Scripts\python.exe'
$LLAMA_COMMIT = '5ad1c5da0ad7f6176256b823925aad19134f0263'
$Sources = @{
  '2B' = @{ Dir = Join-Path $Lab 'models\qwen35_2b\source_hf'; Rev = '15852e8c16360a2fea060d615a32b45270f8a8fc'; Files = @('Qwen3.5-2B-F16.gguf', 'Qwen3.5-2B-Q8_0.gguf', 'Qwen3.5-2B-Q4_K_M.gguf') }
  '4B' = @{ Dir = Join-Path $Lab 'models\qwen35_4b\source_hf'; Rev = '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'; Files = @('Qwen3.5-4B-Q8_0.gguf', 'Qwen3.5-4B-Q4_K_M.gguf') }
}
$Fail = 0
function Check($Name, $Cond, $Detail = '') {
  if ($Cond) { Write-Host "[OK] $Name $Detail" } else { Write-Host "[FAIL] $Name $Detail"; $script:Fail++ }
}
function Sha256($Path) { return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLower() }

# ---------- 1. Preflight (read-only) ----------
Write-Host '=== preflight (read-only) ==='
foreach ($b in @('llama-server.exe', 'llama-cli.exe', 'llama-bench.exe', 'llama-quantize.exe')) {
  Check "bin $b" (Test-Path (Join-Path $Bin $b))
}
Check 'cublas/cudart next to b11457 (else copy from tools\cudart-llama-bin-win-cuda-13.4-x64.zip)' `
  ((Test-Path (Join-Path $Bin 'cublas64_13.dll')) -and (Test-Path (Join-Path $Bin 'cudart64_13.dll')))
Check 'venv python' (Test-Path $VenvPy)
$pkgs = & $VenvPy -c "import importlib.util as u; print('torch',bool(u.find_spec('torch'))); print('transformers',bool(u.find_spec('transformers'))); print('gguf',bool(u.find_spec('gguf')))" 2>&1
Write-Host ($pkgs -join "`n")
Check 'pyTorch present' ($pkgs -match 'torch True')
Check 'transformers present' ($pkgs -match 'transformers True')
Check 'gguf package present (pip install from llama.cpp gguf-py @ 5ad1c5da0 if missing)' ($pkgs -match 'gguf True')
foreach ($m in $Model) {
  $s = $Sources[$m]
  Check "source $m dir" (Test-Path (Join-Path $s.Dir 'config.json')) $s.Dir
  Check "source $m safetensors" ((Get-ChildItem (Join-Path $s.Dir '*.safetensors') -ErrorAction SilentlyContinue).Count -gt 0)
}
if ($ConverterScript -ne '') {
  Check 'converter file' (Test-Path $ConverterScript) $ConverterScript
  if (Test-Path $ConverterScript) {
    $qwenModule = Join-Path (Split-Path $ConverterScript -Parent) 'conversion\qwen.py'
    Check 'modular converter Qwen implementation exists' (Test-Path $qwenModule)
    if (Test-Path $qwenModule) {
      $txt = Get-Content $qwenModule -Raw
      Check 'converter registers Qwen3_5ForConditionalGeneration' ($txt -match 'ModelBase.register\("Qwen3_5ForConditionalGeneration"')
    }
  }
} else { Check 'converter supplied via -ConverterScript' $false '(required before -Execute)' }
$freeD = (Get-PSDrive D).Free / 1GB
Check 'free space on D >= 40 GB' ($freeD -ge 40) ("{0:N1} GB free" -f $freeD)
if ($Fail -gt 0) { Write-Host "PREFLIGHT FAILED ($Fail). Resolve before -Execute."; exit 1 }
Write-Host 'preflight passed.'
if (-not $Execute) { Write-Host 'Dry run only. Re-run with -Execute after review.'; exit 0 }

# ---------- 2. Heavy steps (reviewed execution only) ----------
if ($ConverterScript -eq '' -or -not (Test-Path $ConverterScript)) { throw 'Converter missing. Aborting.' }
$convTxt = Get-Content (Join-Path (Split-Path $ConverterScript -Parent) 'conversion\qwen.py') -Raw
if ($convTxt -notmatch 'Qwen3_5ForConditionalGeneration') { throw 'Converter lacks Qwen3.5 support. STOP: resolve compatibility, do not substitute silently.' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$logDir = Join-Path $Lab 'logs\qwen_convert_b11457'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
& $VenvPy $ConverterScript --help > (Join-Path $logDir 'converter_help.txt') 2>&1
$record = @()
foreach ($m in $Model) {
  $s = $Sources[$m]
  $base = Join-Path $OutDir "Qwen3.5-${m}-F16.gguf"
  if (Test-Path $base) { throw "Refusing to overwrite existing $base. Rename/archive first (never substitute silently)." }
  Write-Host "=== converting Qwen3.5-$m HF -> F16 ==="
  # Text-only: Qwen3.5 ckpts carry a vision tower; no mmproj is produced or used.
  & $VenvPy $ConverterScript $s.Dir --outfile $base --outtype f16 --no-nextn 2>&1 | Tee-Object (Join-Path $logDir "convert_${m}.log")
  if ($LASTEXITCODE -ne 0) { throw "Converter failed for $m (exit $LASTEXITCODE). Output is not a valid completed artifact." }
  if (-not (Test-Path $base)) { throw "Converter produced no output for $m." }
  # GGUF header sanity (magic 'GGUF'), read-only.
  $fs = [System.IO.File]::OpenRead($base); $buf = New-Object byte[] 4; $fs.Read($buf, 0, 4) | Out-Null; $fs.Close()
  if ([System.Text.Encoding]::ASCII.GetString($buf) -ne 'GGUF') { throw "Bad GGUF magic in $base." }
  $targets = @{ '2B' = @('Q8_0', 'Q4_K_M'); '4B' = @('Q8_0', 'Q4_K_M') }[$m]
  foreach ($q in $targets) {
    $dst = Join-Path $OutDir "Qwen3.5-${m}-${q}.gguf"
    if (Test-Path $dst) { throw "Refusing to overwrite existing $dst." }
    Write-Host "=== quantize $m -> $q ==="
    & $Quantize $base $dst $q 2>&1 | Tee-Object (Join-Path $logDir "quantize_${m}_${q}.log")
    if ($LASTEXITCODE -ne 0) { throw "Quantizer failed for ${m}/${q} (exit $LASTEXITCODE)." }
    $record += [pscustomobject]@{ model = "Qwen3.5-$m"; quant = $q; file = $dst; bytes = (Get-Item $dst).Length; sha256 = (Sha256 $dst) }
  }
  $record += [pscustomobject]@{ model = "Qwen3.5-$m"; quant = 'F16'; file = $base; bytes = (Get-Item $base).Length; sha256 = (Sha256 $base) }
  if ($m -eq '4B') { Write-Host 'NOTE: 4B F16 is an intermediate; keep until Q8_0+Q4_K_M hashes are recorded, then archive per main-agent decision.' }
}
$rec = [pscustomobject]@{
  llama_build = 'b11457'; llama_commit = $LLAMA_COMMIT; converter = $ConverterScript; converter_sha256 = (Sha256 $ConverterScript)
  recipe = 'convert_hf_to_gguf.py --outtype f16 --no-nextn (text-only default); llama-quantize.exe F16 Q8_0/Q4_K_M; retain 4B F16 as untested intermediate'
  sources = @{ '2B' = $Sources['2B'].Rev; '4B' = $Sources['4B'].Rev }
  date_utc = (Get-Date).ToUniversalTime().ToString('o'); outputs = $record
}
$rec | ConvertTo-Json -Depth 5 | Out-File (Join-Path $Lab 'manifests\qwen_conversion_record_120.json') -Encoding utf8
Write-Host 'done. Record: manifests\qwen_conversion_record_120.json'

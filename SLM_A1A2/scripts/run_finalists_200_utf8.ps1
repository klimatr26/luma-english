# Explicit text transport; the frozen Python/native generation settings stay unchanged.
$ErrorActionPreference = 'Stop'
$lab = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$previousEncoding = $env:PYTHONIOENCODING
try {
    $env:PYTHONIOENCODING = 'utf-8'
    & (Join-Path $lab '.venv/Scripts/python.exe') -u (Join-Path $lab 'run_finalists_200.py') --execute --benchmark-sha256 ecfe10cf6942788bfa059379e0461ab9e6291a00b5ef330bc806d94cb21dc125
    $result = $LASTEXITCODE
} finally {
    $env:PYTHONIOENCODING = $previousEncoding
}
exit $result

param([Parameter(Mandatory)][string] $LibraryDirectory)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$manifest = Get-Content -LiteralPath "$root/native/TURNIP_MANIFEST.json" -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $LibraryDirectory).Path
$output = "$root/native/artifacts/b12359/turnip-runtime.zip"
foreach ($file in $manifest.files) {
    $path = Join-Path $source $file.name
    if ((Get-Item -LiteralPath $path).Length -ne $file.bytes -or
        (Get-FileHash -LiteralPath $path).Hash -ine $file.sha256) {
        throw "Driver dependency differs from the pinned manifest: $($file.name)"
    }
}
Add-Type -AssemblyName System.IO.Compression
$temporary = "$output.tmp"
if (Test-Path -LiteralPath $temporary) { throw 'An earlier bundle build is incomplete.' }
$zip = [IO.Compression.ZipFile]::Open($temporary,[IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in $manifest.files) {
        $entry = $zip.CreateEntry($file.name,[IO.Compression.CompressionLevel]::Optimal)
        $entry.LastWriteTime = [DateTimeOffset]::new(2026,11,13,0,0,0,[TimeSpan]::Zero)
        $input = [IO.File]::OpenRead((Join-Path $source $file.name))
        $stream = $entry.Open()
        try { $input.CopyTo($stream) }
        finally { $stream.Dispose(); $input.Dispose() }
    }
} finally { $zip.Dispose() }
[IO.File]::Move($temporary,$output,$true)
Get-FileHash -LiteralPath $output -Algorithm SHA256

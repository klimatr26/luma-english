param([switch]$Open)
$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$project = [xml](Get-Content -LiteralPath (Join-Path $appRoot 'Course.Desktop\Course.Desktop.csproj') -Raw)
$version = $project.SelectSingleNode('//Version').InnerText
$destination = Join-Path $appRoot "artifacts\windows-$version"
$nativeRoot = Join-Path $appRoot '..\cross_demo\native\artifacts\b12359-adaptive-v1\win-x64'
foreach ($file in @('writing_worker.exe','writing_llama_bridge.dll','ggml-vulkan.dll','ggml-cpu.dll','llama.dll','llama-common.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $nativeRoot $file))) { throw "Falta el runtime verificado: $file. Consulta el README; no se reemplaza el motor automáticamente." }
}
Push-Location $appRoot
try {
    & dotnet publish Course.Desktop/Course.Desktop.csproj -c Release -r win-x64 --self-contained true -p:PublishTrimmed=false -p:PublishSingleFile=false -o $destination --nologo
    if ($LASTEXITCODE -ne 0) { throw 'Falló la publicación de Windows.' }
    Copy-Item -LiteralPath (Join-Path $appRoot 'README.md') -Destination (Join-Path $destination 'LEEME.md')
    Copy-Item -LiteralPath (Join-Path $appRoot 'THIRD_PARTY_NOTICES.md') -Destination $destination
    $records = @(Get-ChildItem -LiteralPath $destination -File -Recurse | Where-Object { $_.Name -ne 'files.sha256.json' } | ForEach-Object {
        [pscustomobject]@{path=[IO.Path]::GetRelativePath($destination,$_.FullName);bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
    $records | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $destination 'files.sha256.json') -Encoding utf8NoBOM
    $archive = Join-Path $appRoot "artifacts\LumaEnglish-Windows-x64-$version.zip"
    Compress-Archive -LiteralPath $destination -DestinationPath $archive -Force
    Write-Output "Aplicación: $(Join-Path $destination 'LumaEnglish.exe')"
    Write-Output "Paquete: $archive"
    if ($Open) { Start-Process -FilePath (Join-Path $destination 'LumaEnglish.exe') -WindowStyle Normal }
}
finally { Pop-Location }

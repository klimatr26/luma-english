param(
    [string] $OutputDirectory = '',
    [switch] $Open
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { $OutputDirectory = Join-Path $projectRoot 'artifacts\windows-0.1.6' }
[xml]$props = Get-Content -LiteralPath (Join-Path $projectRoot 'Directory.Build.props') -Raw
$nativeRoot = Join-Path $projectRoot "native\artifacts\$($props.Project.PropertyGroup.WritingNativeBuild)\win-x64"
foreach ($library in @('writing_worker.exe','writing_llama_bridge.dll','llama.dll','llama-common.dll','ggml.dll','ggml-base.dll','ggml-cpu.dll','ggml-vulkan.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $nativeRoot $library) -PathType Leaf)) {
        throw "Falta $library. Prepara primero el runtime según WritingApp.Native/README.md; no se publicará una aplicación sin motor."
    }
}
Push-Location -LiteralPath $projectRoot
try {
    # Separate configuration avoids sharing obj/Release with a simultaneous Android publish.
    & dotnet publish 'WritingApp.Desktop/WritingApp.Desktop.csproj' -c DesktopRelease -p:Optimize=true -r win-x64 --self-contained false -o $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Falló la publicación Windows.' }
    $executable = Join-Path ([IO.Path]::GetFullPath($OutputDirectory)) 'WritingApp.Desktop.exe'
    Write-Output $executable
    if ($Open) { Start-Process -FilePath $executable -WorkingDirectory $projectRoot -WindowStyle Normal }
}
finally { Pop-Location }

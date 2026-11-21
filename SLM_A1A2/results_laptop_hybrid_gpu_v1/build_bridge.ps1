$ErrorActionPreference = 'Stop'
$lab = Split-Path -Parent $PSScriptRoot
$source = Join-Path $lab 'cross_demo/native/src/writing_llama_bridge.cpp'
$frozen = Get-Content -LiteralPath (Join-Path $lab 'manifests/finalists_200_20261117.json') -Raw | ConvertFrom-Json

function Get-Sha($Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

$sourceBinding = $frozen.source_bindings | Where-Object { $_.path -like '*\src\writing_llama_bridge.cpp' }
$sourceSha = Get-Sha $source
if ($sourceSha -ne $sourceBinding.sha256) { throw 'Frozen bridge source hash mismatch.' }

$artifact = Join-Path $PSScriptRoot 'native'
$null = New-Item -ItemType Directory -Path $artifact
$original = Join-Path $lab 'cross_demo/native/artifacts/b12359/win-x64'
$assets = [ordered]@{}
foreach ($binding in ($frozen.source_bindings | Where-Object { $_.path -like '*\win-x64\*.dll' })) {
    $file = Split-Path -Leaf $binding.path
    $path = Join-Path $original $file
    if ((Get-Sha $path) -ne $binding.sha256) { throw "Frozen DLL hash mismatch for $file." }
    if ($file -ne 'writing_llama_bridge.dll') {
        $target = Join-Path $artifact $file
        Copy-Item -LiteralPath $path -Destination $target
        $assets[$file] = Get-Sha $target
        if ($assets[$file] -ne $binding.sha256) { throw "Staged DLL hash mismatch for $file." }
    }
}
if ($assets.Count -ne 6) { throw 'Expected six unchanged dependency DLLs.' }

$env:WG_HYBRID_BUILD = (New-Item -ItemType Directory -Path (Join-Path $env:TEMP ('wg-hybrid-' + [guid]::NewGuid().ToString('N')))).FullName
$env:WG_HYBRID_OUT = $artifact
$env:WG_HYBRID_HEADERS = Join-Path $lab 'cross_demo/native/include'
$env:WG_HYBRID_LLAMA = Join-Path $lab ("tools/llama.cpp/llama.cpp-" + $frozen.llama_cpp_commit)
$env:WG_HYBRID_LIB = Join-Path $lab 'cross_demo/native/build/b12359-win-x64/llama.cpp'

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$env:WG_HYBRID_VCVARS = Join-Path $vs 'VC/Auxiliary/Build/vcvars64.bat'
$marker = '    model_params.n_gpu_layers = use_gpu ? -1 : 0;'
$patch = @'
    model_params.n_gpu_layers = use_gpu ? -1 : 0;
    if (use_gpu) {
        const char * layers = std::getenv("WG_HYBRID_GPU_LAYERS");
        if (layers != nullptr) {
            model_params.n_gpu_layers = std::stoi(layers);
        }
    }
'@
$sourceText = [IO.File]::ReadAllText($source)
if ([regex]::Matches($sourceText,[regex]::Escape($marker)).Count -ne 1) { throw 'Bridge selector not unique.' }
$variant = Join-Path $env:WG_HYBRID_BUILD 'writing_llama_bridge.cpp'
[IO.File]::WriteAllText($variant, $sourceText.Replace($marker,$patch.Replace("`r`n","`n")), [Text.UTF8Encoding]::new($false))

$build = Join-Path $env:WG_HYBRID_BUILD 'build.cmd'
@'
@echo off
call "%WG_HYBRID_VCVARS%" >nul
if errorlevel 1 exit /b 1
cl /nologo /LD /std:c++17 /EHsc /O2 /Ob2 /MD /utf-8 /DNDEBUG /DGGML_BACKEND_DL /DGGML_SHARED /DLLAMA_SHARED /DWRITING_LLAMA_BRIDGE_BUILD /I"%WG_HYBRID_HEADERS%" /I"%WG_HYBRID_LLAMA%\common" /I"%WG_HYBRID_LLAMA%\vendor" /I"%WG_HYBRID_LLAMA%\include" /I"%WG_HYBRID_LLAMA%\ggml\include" /Fo"%WG_HYBRID_BUILD%\bridge.obj" /Fe"%WG_HYBRID_OUT%\writing_llama_bridge.dll" "%WG_HYBRID_BUILD%\writing_llama_bridge.cpp" /link /INCREMENTAL:NO /IMPLIB:"%WG_HYBRID_BUILD%\bridge.lib" "%WG_HYBRID_LIB%\common\llama-common.lib" "%WG_HYBRID_LIB%\common\llama-common-base.lib" "%WG_HYBRID_LIB%\src\llama.lib" "%WG_HYBRID_LIB%\ggml\src\ggml.lib" "%WG_HYBRID_LIB%\ggml\src\ggml-base.lib"
'@ | Set-Content -LiteralPath $build -Encoding ascii
cmd.exe /d /c $build
if ($LASTEXITCODE -ne 0) { throw 'Experimental bridge compile failed.' }
$assets['writing_llama_bridge.dll'] = Get-Sha (Join-Path $artifact 'writing_llama_bridge.dll')
[ordered]@{
    original_bridge_source_sha256 = $sourceSha
    experimental_bridge_source_sha256 = (Get-Sha $variant)
    selector_replacement = $patch
    staged_dll_sha256 = $assets
    frozen_manifest_sha256 = (Get-Sha (Join-Path $lab 'manifests/finalists_200_20261117.json'))
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'bridge_build.json') -Encoding utf8NoBOM

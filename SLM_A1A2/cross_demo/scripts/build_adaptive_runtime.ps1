param([ValidateSet('Windows','Android','All')][string]$Platform = 'All')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$lab = Split-Path -Parent $root
$upstream = Join-Path $lab 'tools/llama.cpp/llama.cpp-b1b770d90d94cad9e9ea5b993bdbc383a522fb28'
$old = Join-Path $root 'native/artifacts/b12359'
$output = Join-Path $root 'native/artifacts/b12359-adaptive-v1'
$headers = Join-Path $root 'native/include'
$bridge = Join-Path $root 'native/src/writing_llama_bridge_adaptive.cpp'
$worker = Join-Path $root 'native/tools/inference_worker_adaptive.cpp'
$ndk = Join-Path $env:LOCALAPPDATA 'Android/Sdk/ndk/29.0.14206865'
$vulkan = Join-Path $root 'native/build/deps/Vulkan-Headers-v1.3.275/Vulkan-Headers-1.3.275/include'
$null = New-Item -ItemType Directory -Force -Path $output
if ($Platform -in @('All','Windows')) {
    $dest = Join-Path $output 'win-x64'
    $null = New-Item -ItemType Directory -Force -Path $dest
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $old 'win-x64') -Filter '*.dll' -File) {
        if ($file.Name -ne 'writing_llama_bridge.dll') { Copy-Item -LiteralPath $file.FullName -Destination $dest }
    }
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    $env:WG_ADAPTIVE_VCVARS = Join-Path $vs 'VC/Auxiliary/Build/vcvars64.bat'
    $env:WG_ADAPTIVE_BUILD = (New-Item -ItemType Directory -Force -Path (Join-Path $root 'native/build/adaptive-win-x64')).FullName
    $env:WG_ADAPTIVE_HEADERS = $headers
    $env:WG_ADAPTIVE_UPSTREAM = $upstream
    $env:WG_ADAPTIVE_VULKAN = $vulkan
    $env:WG_ADAPTIVE_LIB = Join-Path $root 'native/build/b12359-win-x64/llama.cpp'
    $env:WG_ADAPTIVE_OUT = $dest
    $env:WG_ADAPTIVE_BRIDGE = $bridge
    $env:WG_ADAPTIVE_WORKER = $worker
    $commands = Join-Path $env:WG_ADAPTIVE_BUILD 'build.cmd'
    @'
@echo off
call "%WG_ADAPTIVE_VCVARS%" >nul
if errorlevel 1 exit /b 1
cl /nologo /LD /std:c++17 /EHsc /O2 /MD /utf-8 /DNDEBUG /DGGML_BACKEND_DL /DGGML_SHARED /DLLAMA_SHARED /DWRITING_LLAMA_BRIDGE_BUILD /I"%WG_ADAPTIVE_HEADERS%" /I"%WG_ADAPTIVE_UPSTREAM%\common" /I"%WG_ADAPTIVE_UPSTREAM%\vendor" /I"%WG_ADAPTIVE_UPSTREAM%\include" /I"%WG_ADAPTIVE_UPSTREAM%\ggml\include" /Fo"%WG_ADAPTIVE_BUILD%\bridge.obj" /Fe"%WG_ADAPTIVE_OUT%\writing_llama_bridge.dll" "%WG_ADAPTIVE_BRIDGE%" /link /INCREMENTAL:NO /IMPLIB:"%WG_ADAPTIVE_BUILD%\bridge.lib" "%WG_ADAPTIVE_LIB%\common\llama-common.lib" "%WG_ADAPTIVE_LIB%\common\llama-common-base.lib" "%WG_ADAPTIVE_LIB%\src\llama.lib" "%WG_ADAPTIVE_LIB%\ggml\src\ggml.lib" "%WG_ADAPTIVE_LIB%\ggml\src\ggml-base.lib"
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /O2 /MT /utf-8 /DNDEBUG /I"%WG_ADAPTIVE_HEADERS%" /I"%WG_ADAPTIVE_UPSTREAM%\vendor" /I"%WG_ADAPTIVE_VULKAN%" /Fo"%WG_ADAPTIVE_BUILD%\worker.obj" /Fe"%WG_ADAPTIVE_OUT%\writing_worker.exe" "%WG_ADAPTIVE_WORKER%" /link /INCREMENTAL:NO
'@ | Set-Content -LiteralPath $commands -Encoding ascii
    & cmd.exe /d /c $commands
    if ($LASTEXITCODE -ne 0) { throw 'Adaptive Windows native build failed.' }
}
if ($Platform -in @('All','Android')) {
    $clang = Join-Path $ndk 'toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe'
    foreach ($abi in @('arm64-v8a','x86_64')) {
        $dest = Join-Path $output "android-$abi"
        $original = Join-Path $old "android-$abi"
        $null = New-Item -ItemType Directory -Force -Path $dest
        foreach ($file in Get-ChildItem -LiteralPath $original -Filter '*.so' -File) {
            if ($file.Name -notin @('libwriting_llama_bridge.so','libwriting_worker.so')) { Copy-Item -LiteralPath $file.FullName -Destination $dest }
        }
        $triple = if ($abi -eq 'arm64-v8a') { 'aarch64-linux-android26' } else { 'x86_64-linux-android26' }
        & $clang "--target=$triple" -std=c++17 -O2 -fPIC -shared '-Wl,-z,max-page-size=16384' `
            -DWRITING_LLAMA_BRIDGE_BUILD -DGGML_BACKEND_DL -DGGML_SHARED -DLLAMA_SHARED `
            "-I$headers" "-I$upstream/common" "-I$upstream/vendor" "-I$upstream/include" "-I$upstream/ggml/include" `
            $bridge "$root/native/src/android_vulkan_preflight.cpp" "-L$dest" '-Wl,--no-undefined' `
            -lllama-common -lllama -lggml -lggml-base -llog -ldl -o "$dest/libwriting_llama_bridge.so"
        if ($LASTEXITCODE -ne 0) { throw "Adaptive Android bridge failed for $abi" }
        $workerTriple = if ($abi -eq 'arm64-v8a') { 'aarch64-linux-android28' } else { 'x86_64-linux-android28' }
        & $clang "--target=$workerTriple" -std=c++17 -O2 -fPIE -pie '-Wl,-z,max-page-size=16384' `
            "-I$headers" "-I$upstream/vendor" $worker -ldl -o "$dest/libwriting_worker.so"
        if ($LASTEXITCODE -ne 0) { throw "Adaptive Android worker failed for $abi" }
    }
    Copy-Item -LiteralPath (Join-Path $old 'turnip-runtime.zip') -Destination $output
    Copy-Item -LiteralPath (Join-Path $old 'turnip-notices') -Destination $output -Recurse -Force
}
Write-Output $output

param()
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ndk = Join-Path $env:LOCALAPPDATA 'Android/Sdk/ndk/29.0.14206865'
$clang = Join-Path $ndk 'toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe'
$source = [IO.Path]::GetFullPath((Join-Path $root '../tools/llama.cpp/llama.cpp-b1b770d90d94cad9e9ea5b993bdbc383a522fb28'))
$dest = Join-Path $root 'native/artifacts/b12359/android-arm64-v8a/libwriting_worker.so'
& $clang --target=aarch64-linux-android28 -std=c++17 -O2 -fPIE -pie '-Wl,-z,max-page-size=16384' `
    "-I$root/native/include" "-I$source/vendor" "$root/native/tools/inference_worker.cpp" -o $dest -ldl
if ($LASTEXITCODE -ne 0) { throw 'Failed to build the Android worker.' }
Get-FileHash -LiteralPath $dest -Algorithm SHA256

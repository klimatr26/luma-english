param(
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Release',
    [string] $OutputDirectory = '',
    [switch] $Diagnostics
)

$ErrorActionPreference = 'Stop'
$sdk = if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
$jdk = Join-Path $env:ProgramFiles 'Android\Android Studio\jbr'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dotnetRoot = Join-Path $projectRoot '.tools\dotnet11'
$dotnet = Join-Path $dotnetRoot 'dotnet.exe'
$cliHome = Join-Path $projectRoot '.tools\dotnet-home'
$project = Join-Path $projectRoot 'WritingApp.Android\WritingApp.Android.csproj'
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot 'artifacts\android-0.1.6'
}
$output = [IO.Path]::GetFullPath($OutputDirectory)

if (-not (Test-Path -LiteralPath (Join-Path $sdk 'platforms\android-37.0\android.jar'))) {
    throw "Android API 37.0 is missing from SDK path: $sdk"
}
if (-not (Test-Path -LiteralPath (Join-Path $sdk 'build-tools\37.0.0\aapt2.exe'))) {
    throw "Android build-tools 37.0.0 are missing from SDK path: $sdk"
}
if (-not (Test-Path -LiteralPath (Join-Path $jdk 'bin\javac.exe'))) {
    throw "Android Studio JDK 21 is missing: $jdk"
}
if (-not (Test-Path -LiteralPath $dotnet -PathType Leaf)) {
    throw "The isolated .NET SDK/workload is missing. Run scripts\android_setup_dotnet.ps1 first."
}
[xml]$props = Get-Content -LiteralPath (Join-Path $projectRoot 'Directory.Build.props') -Raw
$nativeRoot = Join-Path $projectRoot "native\artifacts\$($props.Project.PropertyGroup.WritingNativeBuild)"
foreach ($asset in @('android-arm64-v8a/libwriting_worker.so','turnip-runtime.zip')) {
    if (-not (Test-Path -LiteralPath (Join-Path $nativeRoot $asset) -PathType Leaf)) {
        throw "Missing $asset. Prepare the Android worker and packaged driver before publishing."
    }
}
$requiredNativeLibraries = @(
    'libwriting_llama_bridge.so', 'libllama.so', 'libllama-common.so',
    'libggml.so', 'libggml-base.so', 'libggml-cpu.so', 'libc++_shared.so'
)
foreach ($abiDirectory in @('android-arm64-v8a', 'android-x86_64')) {
    $abiRoot = Join-Path $nativeRoot $abiDirectory
    foreach ($library in $requiredNativeLibraries) {
        if (-not (Test-Path -LiteralPath (Join-Path $abiRoot $library) -PathType Leaf)) {
            throw "Required native library $library is missing for $abiDirectory. The APK would not support local inference."
        }
    }
}

# Keep all Android SDK/JDK selection scoped to this PowerShell process.
$env:DOTNET_ROOT = $dotnetRoot
$env:DOTNET_MULTILEVEL_LOOKUP = '0'
$env:DOTNET_CLI_HOME = $cliHome
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:JAVA_HOME = $jdk
$env:PATH = "$dotnetRoot;$sdk\platform-tools;$sdk\emulator;$jdk\bin;$env:PATH"
New-Item -ItemType Directory -Path $output -Force | Out-Null

Push-Location $projectRoot
try {
    & $dotnet publish $project -f 'net11.0-android37.0' -c $Configuration -o $output `
        "-p:AndroidSdkDirectory=$sdk" "-p:JavaSdkDirectory=$jdk" `
        '-p:AndroidPackageFormats=apk' '-p:AndroidCreatePackagePerAbi=false' `
        '-p:PublishReadyToRun=false' "-p:WritingDiagnostics=$($Diagnostics.IsPresent.ToString().ToLowerInvariant())"
    if ($LASTEXITCODE -ne 0) {
        throw "Android publish failed with exit code $LASTEXITCODE. No workload or SDK packages were installed by this script."
    }
}
finally {
    Pop-Location
}

$signedApkName = 'org.kevinlima.writinglab-Signed.apk'
$signedApk = Get-ChildItem -LiteralPath $output -Filter $signedApkName -File -Recurse | Select-Object -First 1
if (-not $signedApk) {
    throw "Publish succeeded but the expected signed APK $signedApkName was not found in $output"
}
$signedApk | Select-Object FullName, Length

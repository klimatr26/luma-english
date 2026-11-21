$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dotnetRoot = Join-Path $projectRoot '.tools\dotnet11'
$dotnetExe = Join-Path $dotnetRoot 'dotnet.exe'
$cliHome = Join-Path $projectRoot '.tools\dotnet-home'
$sdkVersion = '11.0.100-rc.3.26522.148'
$androidManifestSdkVersion = '11.0.100-preview.6'
$androidManifestVersion = '37.0.0-preview.6.59'

if (-not (Test-Path -LiteralPath $dotnetExe -PathType Leaf)) {
    $installer = Join-Path $env:TEMP 'writinglab-dotnet-install.ps1'
    Invoke-WebRequest -Uri 'https://dot.net/v1/dotnet-install.ps1' -OutFile $installer
    & $installer -Version $sdkVersion -InstallDir $dotnetRoot -Architecture x64 -NoPath
    if (-not (Test-Path -LiteralPath $dotnetExe -PathType Leaf)) {
        throw "The isolated .NET SDK was not installed at $dotnetExe"
    }
}

# Isolate SDK resolution, workload records, and first-run data from system .NET.
$env:DOTNET_ROOT = $dotnetRoot
$env:DOTNET_MULTILEVEL_LOOKUP = '0'
$env:DOTNET_CLI_HOME = $cliHome
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:PATH = "$dotnetRoot;$env:PATH"
New-Item -ItemType Directory -Path $cliHome -Force | Out-Null

$sdkOutput = & $dotnetExe --version
if ($LASTEXITCODE -ne 0 -or $sdkOutput.Trim() -ne $sdkVersion) {
    throw "Expected isolated .NET SDK $sdkVersion; got '$sdkOutput'."
}

# RC3 does not have its own Android manifest. This build uses the pinned API 37
# Preview 6 Android manifest alongside the isolated RC3 SDK/runtime packs.
# Read the manifest from the installed Visual Studio .NET layout and copy only
# this Android manifest into the isolated SDK. Never update system workloads.
$manifestSource = Join-Path $env:ProgramFiles "dotnet\sdk-manifests\$androidManifestSdkVersion\microsoft.net.sdk.android\$androidManifestVersion"
$manifestDestination = Join-Path $dotnetRoot "sdk-manifests\$androidManifestSdkVersion\microsoft.net.sdk.android\$androidManifestVersion"
$pinnedManifestFiles = [ordered]@{
    'WorkloadDependencies.json' = 'F9F497E239AB5A5D521A2E0AEF5C7810B8A09CE67E0ED378BF36EA5DE955A3C7'
    'WorkloadManifest.json' = '6A9823ED25D02F01C4D178DE22E6669D57F0408E188F3BABF59BE6138A3749FA'
    'WorkloadManifest.targets' = '860761BFD6FF309CB3AE92E86CFD02D7713CE45F19FE6843AE43E5E1674592DB'
}
if (-not (Test-Path -LiteralPath $manifestSource -PathType Container)) {
    throw "Required Android workload manifest $androidManifestVersion was not found at $manifestSource. Install the matching VS Preview 6 SDK manifest first; this script will not update or install global workloads."
}
New-Item -ItemType Directory -Path $manifestDestination -Force | Out-Null
foreach ($manifestFile in $pinnedManifestFiles.Keys) {
    $sourceFile = Join-Path $manifestSource $manifestFile
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
        throw "Pinned Android workload manifest file is missing: $sourceFile"
    }
    $actualHash = (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash
    if ($actualHash -ne $pinnedManifestFiles[$manifestFile]) {
        throw "Unexpected SHA-256 for $sourceFile. Expected $($pinnedManifestFiles[$manifestFile]); got $actualHash."
    }
    Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $manifestDestination $manifestFile) -Force
}

& $dotnetExe workload install android --skip-manifest-update --include-previews
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the Android workload into the isolated .NET SDK. No system workload was changed."
}

$requiredAndroidPacks = @(
    "Microsoft.Android.Sdk.Windows\$androidManifestVersion",
    "Microsoft.Android.Ref.37\$androidManifestVersion",
    "Microsoft.Android.Runtime.37.android\$androidManifestVersion",
    "Microsoft.Android.Runtime.CoreCLR.37.android-arm64\$androidManifestVersion",
    "Microsoft.Android.Runtime.CoreCLR.37.android-x64\$androidManifestVersion"
)
foreach ($pack in $requiredAndroidPacks) {
    if (-not (Test-Path -LiteralPath (Join-Path $dotnetRoot "packs\$pack") -PathType Container)) {
        throw "The isolated Android workload is missing required .NET pack $pack."
    }
}

& $dotnetExe workload list
if ($LASTEXITCODE -ne 0) { throw 'Could not list the isolated .NET workloads.' }

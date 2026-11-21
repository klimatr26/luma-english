param(
    [string] $ApkPath = '',
    [string] $AvdName = 'Medium_Phone_API_36.1',
    [int] $BootTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$sdk = if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
$adb = Join-Path $sdk 'platform-tools\adb.exe'
$emulator = Join-Path $sdk 'emulator\emulator.exe'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$package = 'org.kevinlima.writinglab'

if ([string]::IsNullOrWhiteSpace($ApkPath)) {
    $ApkPath = Join-Path $projectRoot 'artifacts\android-0.1.5\org.kevinlima.writinglab-Signed.apk'
}
$ApkPath = [IO.Path]::GetFullPath($ApkPath)
if (-not (Test-Path -LiteralPath $ApkPath -PathType Leaf)) { throw "APK does not exist: $ApkPath" }
if (-not (Test-Path -LiteralPath $adb -PathType Leaf)) { throw "adb.exe is missing: $adb" }
if (-not (Test-Path -LiteralPath $emulator -PathType Leaf)) { throw "emulator.exe is missing: $emulator" }

$availableAvds = @(& $emulator -list-avds)
if ($LASTEXITCODE -ne 0 -or $availableAvds -notcontains $AvdName) {
    throw "AVD '$AvdName' is not configured. Available AVDs: $($availableAvds -join ', ')"
}
$existing = @(& $adb devices | Select-String '^emulator-\d+\s+device')
if ($existing.Count -eq 0) {
    Start-Process -FilePath $emulator -ArgumentList @(
        '-avd', $AvdName, '-memory', '4096', '-read-only', '-no-snapshot-save',
        '-no-window', '-no-audio', '-no-boot-anim'
    ) -WindowStyle Hidden | Out-Null
}

$deadline = [DateTime]::UtcNow.AddSeconds($BootTimeoutSeconds)
do {
    $ready = (& $adb -e shell getprop sys.boot_completed 2>$null | Out-String).Trim()
    if ($ready -eq '1') { break }
    Start-Sleep -Seconds 3
} while ([DateTime]::UtcNow -lt $deadline)
if ($ready -ne '1') { throw "AVD did not finish booting within $BootTimeoutSeconds seconds." }

& $adb -e install -r $ApkPath
if ($LASTEXITCODE -ne 0) { throw "adb install failed with exit code $LASTEXITCODE" }
& $adb -e shell monkey -p $package 1
if ($LASTEXITCODE -ne 0) { throw "Could not launch $package on the emulator." }
Start-Sleep -Seconds 5
$appPid = (& $adb -e shell pidof $package | Out-String).Trim()
if ([string]::IsNullOrWhiteSpace($appPid)) { throw "The app process did not remain running after launch." }
"Installed and launched $package on $AvdName; Android process id: $appPid"

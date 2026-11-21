param(
    [ValidateSet('android-arm64','android-x64')][string]$Runtime = 'android-arm64',
    [switch]$Automation
)
$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$project = [xml](Get-Content -LiteralPath (Join-Path $appRoot 'Course.Android\Course.Android.csproj') -Raw)
$version = $project.SelectSingleNode('//ApplicationDisplayVersion').InnerText
$sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$java = 'C:\Program Files\Android\Android Studio\jbr'
if (-not (Test-Path -LiteralPath (Join-Path $sdk 'platforms\android-37.0\android.jar'))) { throw 'Falta Android SDK 37.0.' }
if (-not (Test-Path -LiteralPath (Join-Path $java 'bin\javac.exe'))) { throw 'Falta el JDK 21 de Android Studio.' }
$variant = if ($Automation) { "$Runtime-automation" } else { $Runtime }
$destination = Join-Path $appRoot "artifacts\android-$version\$variant"
Push-Location $appRoot
try {
    $automationValue = $Automation.IsPresent.ToString().ToLowerInvariant()
    & dotnet publish Course.Android/Course.Android.csproj -c Release -r $Runtime --self-contained true `
        "-p:AndroidSdkDirectory=$sdk" "-p:JavaSdkDirectory=$java" "-p:CourseAutomation=$automationValue" `
        -p:PublishReadyToRun=false -o $destination --nologo
    if ($LASTEXITCODE -ne 0) { throw 'Falló la publicación de Android.' }
    $apk = Join-Path $destination 'org.kevinlima.writinglab-Signed.apk'
    if (-not (Test-Path -LiteralPath $apk)) { throw 'La compilación no produjo el APK firmado esperado.' }
    $delivery = Join-Path $appRoot "artifacts\LumaEnglish-Android-$variant-$version.apk"
    Copy-Item -LiteralPath $apk -Destination $delivery
    Get-FileHash -LiteralPath $delivery -Algorithm SHA256
    Write-Output "APK: $delivery"
}
finally { Pop-Location }

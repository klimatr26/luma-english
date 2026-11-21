param([int]$Port = 5580)
$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$avdRoot = Join-Path $env:USERPROFILE '.android\avd'
$name = 'Luma_English_API_36_1'
$folder = Join-Path $appRoot 'artifacts\android-1.1.0\Luma_English.avd'
$index = Join-Path $avdRoot "$name.ini"
$original = Join-Path $avdRoot 'Medium_Phone.avd\config.ini'
$config = Join-Path $folder 'config.ini'
if (Test-Path -LiteralPath $index) {
    if (-not ((Get-Content -LiteralPath $index) -contains "path=$folder")) { throw 'Ya existe un AVD con ese nombre en otra ruta.' }
}
else {
    if (-not (Test-Path -LiteralPath $original)) { throw 'Falta el perfil Medium_Phone de referencia. No se descarga una imagen automáticamente.' }
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $lines = Get-Content -LiteralPath $original | ForEach-Object {
        if ($_ -match '^AvdId=') { "AvdId=$name" }
        elseif ($_ -match '^avd.ini.displayname=') { 'avd.ini.displayname=Luma English test Android 16' }
        elseif ($_ -match '^disk.dataPartition.size=') { 'disk.dataPartition.size=16G' }
        elseif ($_ -match '^hw.ramSize=') { 'hw.ramSize=4096' }
        else { $_ }
    }
    $lines | Set-Content -LiteralPath $config -Encoding utf8NoBOM
    @('avd.ini.encoding=UTF-8', "path=$folder", 'target=android-36.1') | Set-Content -LiteralPath $index -Encoding utf8NoBOM
}
$logs = Join-Path $appRoot 'artifacts\android-1.1.0'
$process = Start-Process -FilePath "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" `
    -ArgumentList @('-avd',$name,'-port',"$Port",'-no-snapshot-load','-no-snapshot-save','-no-window','-no-audio','-no-boot-anim') `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'emulator.stdout.log') -RedirectStandardError (Join-Path $logs 'emulator.stderr.log')
Write-Output "AVD: $name; PID: $($process.Id); ADB: emulator-$Port; datos: $folder"

$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    & dotnet publish '.\WritingDemo.WinForms\WritingDemo.WinForms.csproj' -c Release --no-self-contained -o '.\publish'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar la aplicación.' }
    Start-Process -FilePath (Join-Path $PSScriptRoot 'publish\WritingDemo.WinForms.exe') -WorkingDirectory $PSScriptRoot -WindowStyle Normal
}
finally { Pop-Location }

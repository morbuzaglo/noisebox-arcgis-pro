<#
.SYNOPSIS
  Builds the NoiseBox ArcGIS Pro add-in and packages it as dist\NoiseBox.esriAddinX.
.DESCRIPTION
  Needs the .NET SDK (8 or newer; built and checked with 11.0.100) and internet for the Esri NuGet package
  (Esri.ArcGISPro.Extensions30, used only for the reference assemblies). ArcGIS Pro 3.5 must be installed.
  Esri's own packaging target needs Visual Studio's MSBuild, so this script builds with `dotnet build` and zips the
  add-in itself, in the same layout (Config.daml at the root, assemblies under Install\).
  The finished .esriAddinX can be copied to any computer with ArcGIS Pro 3.5 and installed by double-click; that computer
  does not need the SDK.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$projDir = Join-Path $root "addin\NoiseBoxAddin"

$sdks = & dotnet --list-sdks 2>$null
if (-not $sdks) {
    Write-Host "No .NET SDK found. Install one with:  winget install Microsoft.DotNet.SDK.8" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "C:\Program Files\ArcGIS\Pro\bin\ArcGISPro.exe")) {
    Write-Host "ArcGIS Pro was not found in C:\Program Files\ArcGIS\Pro." -ForegroundColor Red
    exit 1
}
& dotnet build (Join-Path $projDir "NoiseBoxAddin.csproj") -c Release --nologo
if ($LASTEXITCODE -ne 0) { Write-Host "Build failed. See the messages above." -ForegroundColor Red; exit $LASTEXITCODE }

$out = Join-Path $projDir "bin\Release\net8.0-windows"
$stage = Join-Path ([IO.Path]::GetTempPath()) ("noisebox_addin_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force (Join-Path $stage "Install") | Out-Null
Copy-Item (Join-Path $projDir "Config.daml") $stage
Copy-Item (Join-Path $out "NoiseBoxAddin.dll") (Join-Path $stage "Install")

$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
$zip = Join-Path $dist "NoiseBox.zip"
$final = Join-Path $dist "NoiseBox.esriAddinX"
Remove-Item $zip, $final -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip)
Move-Item $zip $final
Remove-Item $stage -Recurse -Force
Write-Host "Built: $final" -ForegroundColor Green
Write-Host "Install: close ArcGIS Pro, double-click the file, choose Install. Then open Pro: the NoiseBox tab appears."

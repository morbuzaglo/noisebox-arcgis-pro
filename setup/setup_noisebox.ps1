<#
  NoiseBox one-time setup on a new computer.
  Creates %LOCALAPPDATA%\NoiseBox\venv310 (Python 3.10) and installs numpy + the MATLAB Engine for Python into it.
  Needs: Python 3.10 (python.org, 64-bit) and a MATLAB install that supports Python 3.10 (R2022b ... R2024b; not R2025+ with 3.10).
  Usage (PowerShell):  .\setup\setup_noisebox.ps1 [-MatlabRoot "C:\Program Files\MATLAB\R2023a"]
#>
param([string]$MatlabRoot = "")
$ErrorActionPreference = "Stop"

# 1) Python 3.10
$py = $null
try { $py = (& py -3.10 -c "import sys;print(sys.executable)").Trim() } catch {}
if (-not $py) { throw "Python 3.10 not found. Install Python 3.10 (64-bit) from python.org, then re-run." }
Write-Host "Python 3.10: $py"

# 2) MATLAB
if (-not $MatlabRoot) {
    $m = Get-ChildItem "C:\Program Files\MATLAB" -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if ($m) { $MatlabRoot = $m.FullName }
}
if (-not $MatlabRoot -or -not (Test-Path "$MatlabRoot\extern\engines\python\setup.py")) {
    throw "MATLAB not found. Pass -MatlabRoot 'C:\Program Files\MATLAB\R20xxx' (the folder that contains 'bin' and 'extern')."
}
Write-Host "MATLAB: $MatlabRoot"

# 3) venv (outside the OneDrive-synced project folder)
$venv = Join-Path $env:LOCALAPPDATA "NoiseBox\venv310"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    New-Item -ItemType Directory -Force (Split-Path $venv) | Out-Null
    & $py -m venv $venv
}
$vpy = "$venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip numpy
& $vpy -m pip install "$MatlabRoot\extern\engines\python"

# 4) verify
& $vpy -c "import matlab.engine, numpy, sys; print('OK: Python', sys.version.split()[0], '| numpy', numpy.__version__, '| matlab.engine', matlab.engine.__file__)"
Write-Host "`nDone. In ArcGIS Pro run the 'Check MATLAB Link' tool."

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$MaiaPath = Join-Path $ProjectRoot 'scripts\maia3_uci.py'
$CachePath = Join-Path $ProjectRoot 'data\maia-cache'
$TempPath = Join-Path $ProjectRoot 'data\install-temp'

if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Project Python environment is missing. Run the project setup instructions first.' }
if (-not (Test-Path -LiteralPath $MaiaPath)) { throw 'Official Maia-3 source is missing from vendor\maia3.' }
New-Item -ItemType Directory -Force -Path $CachePath, $TempPath | Out-Null
$env:TEMP = $TempPath
$env:TMP = $TempPath

Push-Location $ProjectRoot
try {
    & $PythonPath -m pip install --no-cache-dir -r requirements-maia3.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install Maia-3 runtime dependencies.' }
    & $PythonPath (Join-Path $ProjectRoot 'scripts\cache_maia3.py') --model maia3-5m --cache-dir 'data/maia-cache'
    if ($LASTEXITCODE -ne 0) { throw 'Could not download the Maia-3 5M model.' }
} finally { Pop-Location }
Write-Host 'Maia-3 5M is installed and cached locally. Restart HumanGM Chess AI.'

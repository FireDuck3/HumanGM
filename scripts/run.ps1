param([switch]$RebuildFrontend, [switch]$Restart, [int]$Port = 8006)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$FrontendPath = Join-Path $ProjectRoot 'frontend'
if ($RebuildFrontend) {
    Push-Location $FrontendPath
    try {
        if (-not (Test-Path -LiteralPath (Join-Path $FrontendPath 'node_modules'))) { npm.cmd ci }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath (Join-Path $FrontendPath 'dist\index.html'))) { throw 'Frontend bundle is missing. Run npm install and npm run build in frontend first.' }
if (Test-Path -LiteralPath $PythonPath) {
    $env:PYTHONPATH = $ProjectRoot
} else {
    $PythonPath = 'python'
    $env:PYTHONPATH = (Join-Path $ProjectRoot 'vendor') + ';' + $ProjectRoot
}
$DataPath = Join-Path $ProjectRoot 'data'
New-Item -ItemType Directory -Force -Path $DataPath | Out-Null
$ExistingServer = $false
try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 2 | Out-Null; $ExistingServer = $true }
catch { $ExistingServer = $false }
if ($Restart -and $ExistingServer) {
    $Listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $Stopped = $false
    foreach ($OwnerId in ($Listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $Owner = Get-CimInstance Win32_Process -Filter "ProcessId = $OwnerId" -ErrorAction SilentlyContinue
        if ($Owner -and $Owner.ExecutablePath -ieq $PythonPath -and $Owner.CommandLine -match 'backend\.main:app') {
            Stop-Process -Id $OwnerId -Force
            $Stopped = $true
        }
    }
    if ($Stopped) {
        Start-Sleep -Seconds 1
    } else {
        $OriginalPort = $Port
        $Port = 0
        for ($candidate = $OriginalPort + 1; $candidate -le $OriginalPort + 10; $candidate++) {
            $occupied = @(Get-NetTCPConnection -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue).Count -gt 0
            if (-not $occupied) {
                try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$candidate/healthz" -TimeoutSec 1 | Out-Null; $occupied = $true }
                catch { $occupied = $false }
            }
            if (-not $occupied) { $Port = $candidate; break }
        }
        if ($Port -eq 0) { throw "Could not find a free port from $($OriginalPort + 1) to $($OriginalPort + 10)." }
        Write-Host "Could not safely stop the existing server on port $OriginalPort; starting the updated app on port $Port instead."
    }
}
$StdoutLog = Join-Path $DataPath "server-$Port.log"
$StderrLog = Join-Path $DataPath "server-$Port-error.log"
$ServerReady = $false
try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 2 | Out-Null; $ServerReady = $true }
catch { $ServerReady = $false }
if (-not $ServerReady) {
    Start-Process -FilePath $PythonPath -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',"$Port") -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog
}
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 2 | Out-Null; $ServerReady = $true; break }
    catch { Start-Sleep -Seconds 1 }
}
if (-not $ServerReady) { throw "Backend did not start on 127.0.0.1:$Port. Check Python dependencies and data\server-$Port-error.log." }
Write-Host "HumanGM Chess AI is running at http://127.0.0.1:$Port (API docs: /docs)."
$OpenUrl = "http://127.0.0.1:$Port/"
try { Start-Process $OpenUrl }
catch { Write-Host "Open $OpenUrl in your browser." }

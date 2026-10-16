<#
 start_all.ps1 - starts the whole demo with one command.

   .\start_all.ps1                 3 chain nodes + wallet service + Byte Coffee shop, opens the browser
   .\start_all.ps1 -Stop           stops everything this script started
   .\start_all.ps1 -Rebuild        rebuilds the React UI first
   .\start_all.ps1 -NoBrowser      don't open browser tabs
   .\start_all.ps1 -Autolock 1800  wallet auto-lock in seconds (default 900)
#>
param(
  [switch]$Stop,
  [switch]$Rebuild,
  [switch]$NoBrowser,
  [int]$Autolock = 900
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$pidFile = Join-Path $PSScriptRoot ".demo_pids"

function Stop-Demo {
  if (Test-Path $pidFile) {
    foreach ($id in Get-Content $pidFile) {
      if ($id -match '^\d+$') { cmd /c "taskkill /PID $id /T /F >nul 2>&1" }   # /T also kills python inside
    }
    Remove-Item $pidFile -Force
    Write-Host "Stopped the demo windows." -ForegroundColor Yellow
  } else {
    Write-Host "Nothing to stop."
  }
}

if ($Stop) { Stop-Demo; exit 0 }
if (Test-Path $pidFile) { Write-Host "A previous demo is still running; stopping it first..."; Stop-Demo; Start-Sleep -Seconds 2 }

if (-not (Test-Path $py)) { throw "Python venv not found at $py. Create it first: python -m venv .venv ; pip install -r requirements.txt" }

# ---- are the ports free? ----------------------------------------------------
function Test-PortBusy([int]$port) {
  $c = New-Object System.Net.Sockets.TcpClient
  try { $c.Connect("127.0.0.1", $port); return $true }
  catch { return $false }
  finally { $c.Close() }
}
$busy = @(6000, 6001, 6002, 8000, 8001, 8002, 9000, 9100) | Where-Object { Test-PortBusy $_ }
if ($busy) {
  throw "Ports already in use: $($busy -join ', '). Close old node/service windows, then run again."
}

# ---- build the React wallet if needed -----------------------------------------
$dist = Join-Path $PSScriptRoot "wallet-ui\dist\index.html"
if ($Rebuild -or -not (Test-Path $dist)) {
  Write-Host "Building the React wallet (one-time, about 20 seconds)..." -ForegroundColor Cyan
  Push-Location (Join-Path $PSScriptRoot "wallet-ui")
  try {
    if (-not (Test-Path "node_modules")) {
      npm install
      if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
  } finally { Pop-Location }
}

# ---- helpers --------------------------------------------------------------------
$script:ids = @()
function Start-Window([string]$title, [string]$command) {
  $inner = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$PSScriptRoot'; $command"
  $p = Start-Process powershell -ArgumentList "-NoExit", "-Command", $inner -PassThru
  $script:ids += $p.Id
  $script:ids | Set-Content $pidFile            # saved immediately so -Stop always works
}

function Wait-Until([scriptblock]$cond, [string]$what, [int]$seconds = 45) {
  $end = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $end) {
    try { if (& $cond) { return } } catch { }
    Start-Sleep -Milliseconds 700
  }
  throw "Timed out waiting for $what"
}

# ---- start everything -------------------------------------------------------------
try {
  Write-Host "Starting the 3 validator nodes..." -ForegroundColor Cyan
  foreach ($n in "V1", "V2", "V3") { Start-Window "PoA node $n" "& '$py' run_node.py $n" }
  Wait-Until {
    (8000..8002 | ForEach-Object { (Invoke-RestMethod "http://127.0.0.1:$_/api/status" -TimeoutSec 2).peers -eq 2 }) -notcontains $false
  } "the 3 nodes to connect to each other"

  Write-Host "Starting the wallet service..." -ForegroundColor Cyan
  Start-Window "PoA wallet service" "& '$py' -m mm_wallet.service --autolock $Autolock"
  Wait-Until { (Invoke-RestMethod "http://127.0.0.1:9000/api/state" -TimeoutSec 2) -ne $null } "the wallet service"

  Write-Host "Starting the Byte Coffee demo shop..." -ForegroundColor Cyan
  Start-Window "Byte Coffee shop" "& '$py' dapp_demo.py"
  Wait-Until { (Invoke-WebRequest "http://127.0.0.1:9100" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } "the shop"
}
catch {
  Write-Host "Startup failed: $_" -ForegroundColor Red
  Stop-Demo
  exit 1
}

Write-Host ""
Write-Host "Everything is running." -ForegroundColor Green
Write-Host "  Wallet     http://127.0.0.1:9000"
Write-Host "  Shop       http://127.0.0.1:9100"
Write-Host "  Chain view http://127.0.0.1:8000"
Write-Host ""
Write-Host "  Fund a new wallet:  python wallet.py --user alice send <your address> 200"
Write-Host "  Stop everything:    .\start_all.ps1 -Stop"

if (-not $NoBrowser) {
  Start-Process "http://127.0.0.1:9000"
  Start-Process "http://127.0.0.1:9100"
  Start-Process "http://127.0.0.1:8000"
}
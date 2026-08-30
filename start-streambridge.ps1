$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$entrypoint = Join-Path $projectRoot "run.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python ortamı bulunamadı: $python"
}

$listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "StreamBridge zaten çalışıyor: http://localhost:8080/player/"
    exit 0
}

$quotedEntrypoint = '"' + $entrypoint + '"'
Start-Process -FilePath $python -ArgumentList $quotedEntrypoint `
    -WorkingDirectory $projectRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $projectRoot ".streambridge.out.log") `
    -RedirectStandardError (Join-Path $projectRoot ".streambridge.err.log")

foreach ($attempt in 1..20) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/system/health" `
            -TimeoutSec 2
        Write-Host "StreamBridge $($health.version) çalışıyor: http://localhost:8080/player/"
        exit 0
    }
    catch {
        Start-Sleep -Milliseconds 250
    }
}

throw "StreamBridge başlatıldı ancak sağlık kontrolüne yanıt vermedi."

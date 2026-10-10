# 只在这台电脑上启动 VertexAgent，并打开本机页面。
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$url = "http://127.0.0.1:8765"

function Test-VertexUp {
    try {
        $response = Invoke-WebRequest -Uri "$url/api/health" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (Test-VertexUp) {
    Start-Process $url
    exit 0
}

python -c "import fastapi, uvicorn, httpx, yaml" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m pip install -r requirements.txt
}

Start-Process -WindowStyle Hidden -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile",
    "-Command",
    "for (`$i = 0; `$i -lt 40; `$i++) { try { Invoke-WebRequest -Uri '$url/api/health' -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process '$url'; break } catch { Start-Sleep -Milliseconds 500 } }"
)

python -m vertex_agent

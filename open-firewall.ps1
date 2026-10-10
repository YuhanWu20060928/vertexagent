# 以管理员身份运行后，局域网里的其他电脑才能访问 VertexAgent。
New-NetFirewallRule -DisplayName "VertexAgent TCP 8765" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765
Write-Host "已放行 TCP 8765"

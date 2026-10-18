# ============================================================================
# start-tunnel.ps1  —  Dev-only Cloudflare quick tunnel for phone GPS testing.
#
# Exposes the local Traccar OsmAnd port (localhost:5055) over a temporary
# public HTTPS URL so a phone running the Traccar Client app can reach it
# even when the PC's inbound ports are blocked (Cynet / firewall / router).
#
# Usage:  right-click -> "Run with PowerShell",  OR in a terminal:
#            powershell -ExecutionPolicy Bypass -File C:\Fahad\IzylrnTracker\tools\start-tunnel.ps1
#
# The public URL is printed AND copied to your clipboard. Paste it into the
# Traccar Client app's "Server URL". Keep this window open while testing;
# closing it (or Ctrl+C) stops the tunnel. The URL changes every run.
#
# NOTE: dev-only. Production uses the server's real domain — no tunnel needed.
# ============================================================================

$cf  = Join-Path $PSScriptRoot 'cloudflared.exe'
$log = Join-Path $env:TEMP 'izysafe-tunnel.err.log'
if (Test-Path $log) { Remove-Item $log -Force -ErrorAction SilentlyContinue }

if (-not (Test-Path $cf)) {
  Write-Host "cloudflared.exe not found next to this script ($cf)." -ForegroundColor Red
  exit 1
}

Write-Host 'Starting Cloudflare tunnel to http://localhost:5055 ...' -ForegroundColor Cyan

$proc = Start-Process -FilePath $cf `
  -ArgumentList 'tunnel','--url','http://localhost:5055','--no-autoupdate' `
  -RedirectStandardError $log -RedirectStandardOutput "$log.out" `
  -NoNewWindow -PassThru

try {
  $url = $null
  for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
      $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
      if ($m) { $url = $m.Matches[0].Value; break }
    }
  }

  if ($url) {
    try { $url | Set-Clipboard } catch {}
    Write-Host ''
    Write-Host '====================================================================' -ForegroundColor Green
    Write-Host "  TUNNEL URL:  $url" -ForegroundColor Green
    Write-Host '  (copied to clipboard - paste into Traccar Client > Server URL)'     -ForegroundColor Green
    Write-Host '  Device identifier in the app stays the SAME (your paired IMEI).'    -ForegroundColor Green
    Write-Host '====================================================================' -ForegroundColor Green
    Write-Host ''
    Write-Host 'Keep this window OPEN while testing. Close it or press Ctrl+C to stop.' -ForegroundColor Yellow
  } else {
    Write-Host 'Could not detect the tunnel URL within 25s.' -ForegroundColor Red
    Write-Host "Check that the IzySafe stack is up, then see the log: $log"
  }

  # Keep running until cloudflared exits (or the user closes/Ctrl+C this window).
  Wait-Process -Id $proc.Id
}
finally {
  if ($proc -and -not $proc.HasExited) {
    Write-Host 'Stopping tunnel...' -ForegroundColor Yellow
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  }
}

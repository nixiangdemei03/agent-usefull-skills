# SMS idle monitor — tied to Claude Code lifecycle
# Start this from CLAUDE.md when Claude opens.
# It monitors idle time, compresses when idle >300s,
# and auto-exits when Claude Code closes.

$null = Add-Type @'
using System;using System.Runtime.InteropServices;
public class IC{public struct LI{public uint cb;public uint dt;}
[DllImport("user32.dll")]public static extern bool GetLastInputInfo(ref LI p);}
'@

# ── Config ──
$SMS_MEMORY = "C:\Users\64608\sms-memory"
$COMPRESS_SCRIPT = "$SMS_MEMORY\scripts\compress.py"
$LAST_COMPRESS_FILE = "$SMS_MEMORY\.last_compress"
$CLAUDE_PROCESS = "claude"
$CHECK_INTERVAL = 30

# Ensure last_compress exists
if (-not (Test-Path $LAST_COMPRESS_FILE)) {
  [System.IO.File]::WriteAllText($LAST_COMPRESS_FILE, "0")
}

Write-Host "[SMS-monitor] Started. Monitoring idle while Claude is open..."

$compressed = $false

while ($true) {
  # Check if Claude Code is still running
  $claude = Get-Process -Name $CLAUDE_PROCESS -ErrorAction SilentlyContinue
  if (-not $claude) {
    Write-Host "[SMS-monitor] Claude closed. Running final compress..."
    try {
      wsl python3 "/home/lzx020508/.openclaw/workspace/memory/scripts/compress.py" "--dir" "/mnt/c/Users/64608/sms-memory" 2>&1 | Write-Host
    } catch {
      Write-Host "[SMS-monitor] Final compress error: $($_.Exception.Message)"
    }
    Write-Host "[SMS-monitor] Exiting."
    exit 0
  }

  # Check idle time
  $l = New-Object IC+LI
  $l.cb = [Runtime.InteropServices.Marshal]::SizeOf($l)
  $null = [IC]::GetLastInputInfo([ref]$l)
  $idle = [Math]::Floor(([Environment]::TickCount - $l.dt) / 1000)

  if ($idle -gt 300 -and -not $compressed) {
    $lastTime = [System.IO.File]::ReadAllText($LAST_COMPRESS_FILE).Trim()
    $now = [DateTime]::UtcNow.Ticks
    $lastTicks = [long]0
    [long]::TryParse($lastTime, [ref]$lastTicks) | Out-Null
    $elapsed = [TimeSpan]::FromTicks($now - $lastTicks).TotalSeconds

    if ($elapsed -gt 60) {
      Write-Host "[SMS-monitor] Idle ${idle}s → compressing..."
      try {
        $result = wsl python3 "/home/lzx020508/.openclaw/workspace/memory/scripts/compress.py" "--dir" "/mnt/c/Users/64608/sms-memory" 2>&1
        Write-Host $result
        [System.IO.File]::WriteAllText($LAST_COMPRESS_FILE, [DateTime]::UtcNow.Ticks.ToString())
      } catch {
        Write-Host "[SMS-monitor] Compress error: $($_.Exception.Message)"
      }
    } else {
      Write-Host "[SMS-monitor] Idle ${idle}s, skip (last compress ${elapsed}s ago)"
    }
    $compressed = $true
  }
  if ($idle -le 300) { $compressed = $false }

  Start-Sleep -Seconds $CHECK_INTERVAL
}

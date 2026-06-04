@echo off
REM SMS v4 — Claude Code Launcher
REM Starts idle monitor → runs Claude → on exit: compress + cleanup

REM Start idle monitor (hidden)
start /B powershell -WindowStyle Hidden -File "%USERPROFILE%\.claude\idle-monitor.ps1"

REM Run Claude Code with all original arguments
claude %*

REM Claude exited — final compress
wsl python3 /home/lzx020508/.openclaw/workspace/memory/scripts/compress.py --dir /mnt/c/Users/64608/sms-memory

REM Kill the idle monitor
powershell -Command "Get-Process | Where-Object { $_.MainWindowTitle -eq '' -and $_.ProcessName -eq 'powershell' -and (Get-Process -Id $_.Id -ErrorAction SilentlyContinue) -and ($_.CommandLine -like '*idle-monitor*') } | Stop-Process -Force" 2>nul

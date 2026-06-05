@echo off
@echo off
REM SMS v4 — Claude Code Launcher (v2)
REM Starts both idle monitors → runs Claude → on exit: compress + cleanup

REM Start idle monitors (hidden)
start /B powershell -WindowStyle Hidden -File "%USERPROFILE%\.claude\idle-monitor.ps1"
start /B powershell -WindowStyle Hidden -File "%USERPROFILE%\.claude\idle_monitor.ps1"

REM Run Claude Code with all original arguments
claude %*

REM Claude exited — final compress
REM (Adjust the WSL path below to match your install)
wsl python3 ~/.openclaw/workspace/memory/scripts/compress.py 2>nul

REM Kill idle monitors
powershell -Command "Get-Process | Where-Object { $_.ProcessName -eq 'powershell' -and ($_.CommandLine -like '*idle-monitor*') } | Stop-Process -Force" 2>nul

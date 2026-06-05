# SMS v4 — Idle Monitor for Windows
# 每 10 秒检测一次用户空闲状态，写入文件供 WSL 侧读取。
# 启动: 放到启动项或由 claude-sms.bat 自动拉起。
#
# 输出文件: C:\Users\64608\.claude\idle_state.txt
# 内容: 当前空闲秒数 (浮点数)

$stateFile = "$env:USERPROFILE\.claude\idle_state.txt"
$intervalSec = 10

# 确保目录存在
$dir = Split-Path $stateFile -Parent
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

# 首次加载 System.Windows.Forms (用于 GetLastInputInfo 等效功能)
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue

Write-Host "[SMS-idle] Monitor started. Writing to $stateFile every ${intervalSec}s"

while ($true) {
    try {
        $idle = [System.Windows.Forms.SystemInformation]::IdleTime.TotalSeconds
        $idle | Out-File -FilePath $stateFile -Force -Encoding ASCII
        if ($idle -ge 300) {
            # idle >5min: 只写值，不输出 (避免刷屏)
        }
    } catch {
        # 写错误值 -1 表示不可用
        "-1" | Out-File -FilePath $stateFile -Force -Encoding ASCII
    }
    Start-Sleep -Seconds $intervalSec
}

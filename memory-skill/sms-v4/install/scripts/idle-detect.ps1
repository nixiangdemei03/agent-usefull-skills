# Idle Detection + Compression Trigger
# Monitors GetLastInputInfo, requires 6 consecutive idle samples (>5 min each) before trigger
# Output: "TRIGGER|<idle_sec>" on compression trigger, "RESET" on user return

try {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class IdleDetect {
    [DllImport("user32.dll")]
    public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
    [StructLayout(LayoutKind.Sequential)]
    public struct LASTINPUTINFO {
        public uint cbSize;
        public uint dwTime;
    }
}
"@
} catch {
    # Type already defined from previous run — ignore
}

Write-Output "READY"

$consecutive = 0
$triggered = $false
$idleThreshold = 300   # 5 minutes
$requiredSamples = 6
$sampleInterval = 10   # seconds

while ($true) {
    # Get idle milliseconds via GetLastInputInfo
    $lii = New-Object IdleDetect+LASTINPUTINFO
    $lii.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($lii)
    $null = [IdleDetect]::GetLastInputInfo([ref]$lii)

    $idleMs = [System.Environment]::TickCount - $lii.dwTime
    if ($idleMs -lt 0) { $idleMs += 4294967296 }  # 32-bit wrap-around

    $idleSec = [Math]::Floor($idleMs / 1000)

    if ($idleSec -ge $idleThreshold) {
        $consecutive++
        if ($consecutive -ge $requiredSamples -and -not $triggered) {
            Write-Output "TRIGGER|$idleSec"
            $triggered = $true
        }
    } else {
        if ($triggered) {
            Write-Output "RESET"
        }
        $triggered = $false
        $consecutive = 0
    }

    Start-Sleep -Seconds $sampleInterval
}

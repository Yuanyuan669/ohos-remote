param(
  [string]$Target = "",
  [string]$Token = "123456",
  [int]$Interval = 250,
  [string]$Hdc = "D:\ohos-tools\sdk\openharmony-4.0-Release\toolchains\hdc.exe",
  [string]$Agent = ""
)

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Agent) { $Agent = Join-Path $root "agent\ohos-agent" }

function Hdc-Run {
  param([string[]]$Args)
  if ($Target) { & $Hdc -t $Target @Args } else { & $Hdc @Args }
}

Hdc-Run @("file", "send", $Agent, "/data/local/tmp/ohos-agent") | Out-Null
Hdc-Run @("shell", "kill `$(pidof ohos-agent) 2>/dev/null; chmod +x /data/local/tmp/ohos-agent; nohup /data/local/tmp/ohos-agent -addr :8765 -token $Token -interval $Interval >/data/local/tmp/ohos-agent.log 2>&1 &") | Out-Null
Start-Sleep -Seconds 2

$ip = ""
try {
  $ifc = (Hdc-Run @("shell", "ifconfig wlan0")) -join "`n"
  $m = [regex]::Match($ifc, "inet addr:([0-9.]+)")
  if ($m.Success) { $ip = $m.Groups[1].Value }
} catch { }

Write-Host "agent started."
if ($ip) { Write-Host "open: http://${ip}:8765/?token=$Token" }

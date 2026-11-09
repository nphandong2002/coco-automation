<#
  Điều khiển Coco Automation trên Windows.
    coco start            khởi chạy nền (ẩn cửa sổ), một lệnh cho toàn bộ hệ thống
    coco run              chạy ở cửa sổ này (xem log trực tiếp, Ctrl+C để dừng)
    coco stop | restart | status | logs | open
    coco backup [-DbOnly]            sao lưu DB + storage + .env vào backups\coco-<ngày>.zip
    coco restore <file.zip> [-WithEnv]
    coco autostart on|off            tự chạy khi đăng nhập Windows
    coco firewall                    mở cổng cho máy khác trong mạng LAN (cần quyền Administrator)
#>
param(
  [Parameter(Position = 0)][string]$Command = "help",
  [Parameter(Position = 1)][string]$Arg = "",
  [switch]$DbOnly,
  [switch]$WithEnv,
  [switch]$Yes
)
$ErrorActionPreference = "Stop"
$App = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Py = Join-Path $App ".venv\Scripts\python.exe"
$PidFile = Join-Path $App "run\coco.pid"
$StopFile = Join-Path $App "run\stop.request"
function Info($m) { Write-Host "[coco] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[coco] $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "[coco] $m" -ForegroundColor Red; exit 1 }

function Read-Env {
  $e = @{}
  $f = Join-Path $App ".env"
  if (-not (Test-Path $f)) { Die ".env không tồn tại. Chạy install-windows.cmd trước." }
  foreach ($line in Get-Content $f -Encoding UTF8) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $e[$Matches[1]] = $Matches[2].Trim() }
  }
  return $e
}
$EnvVars = $null
function Cfg($k, $d = "") { if (-not $script:EnvVars) { $script:EnvVars = Read-Env }; if ($script:EnvVars.ContainsKey($k) -and $script:EnvVars[$k] -ne "") { return $script:EnvVars[$k] } else { return $d } }
function Port { [int](Cfg "PORT" "8080") }
function Auth {
  $pw = Cfg "DASHBOARD_PASSWORD"
  if (-not $pw) { return @{} }
  $b = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$(Cfg 'DASHBOARD_USERNAME' 'admin'):$pw"))
  return @{ Authorization = "Basic $b" }
}
function Need-Venv { if (-not (Test-Path $Py)) { Die "Chưa cài đặt. Chạy install-windows.cmd trước." } }
function Running-Pid {
  if (-not (Test-Path $PidFile)) { return $null }
  $p = [int](Get-Content $PidFile -ErrorAction SilentlyContinue)
  if ($p -and (Get-Process -Id $p -ErrorAction SilentlyContinue)) { return $p }
  return $null
}
function Healthy { try { (Invoke-WebRequest "http://127.0.0.1:$(Port)/api/health" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { $false } }

function Do-Start {
  Need-Venv
  if (Running-Pid) { Info "Đang chạy (PID $(Running-Pid))."; return }
  New-Item -ItemType Directory -Force -Path (Join-Path $App "logs"), (Join-Path $App "run") | Out-Null
  Remove-Item $StopFile -ErrorAction SilentlyContinue
  # cmd /c strips the first and last quote when a line has several: wrap the whole command in one more pair
  $cmd = "`"`"$Py`" -m app.tools.supervisor >> `"$App\logs\server.out`" 2>&1`""
  Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd -WorkingDirectory (Join-Path $App "backend") -WindowStyle Hidden
  Info "Đang khởi động (lần đầu có thể mất ~1 phút để bật PostgreSQL và migration)..."
  for ($i = 0; $i -lt 120; $i++) {
    if (Healthy) {
      $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notmatch '^(127|169)\.' } | Select-Object -First 1).IPAddress
      $msg = "Sẵn sàng: http://localhost:$(Port)"
      if ($ip) { $msg += "   (mạng LAN: http://${ip}:$(Port))" }
      Info $msg
      return
    }
    Start-Sleep -Seconds 1
  }
  Die "Chưa phản hồi sau 2 phút. Xem logs\server.out và logs\app.log (hoặc chạy:  coco run)"
}

function Do-Stop {
  $p = Running-Pid
  if (-not $p) { Info "Không có tiến trình nào đang chạy."; Remove-Item $PidFile -ErrorAction SilentlyContinue; return }
  Info "Đang dừng (PID $p) — chờ worker dừng êm, tối đa 90 giây..."
  New-Item -ItemType File -Force -Path $StopFile | Out-Null
  for ($i = 0; $i -lt 90; $i++) { if (-not (Get-Process -Id $p -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
  if (Get-Process -Id $p -ErrorAction SilentlyContinue) {
    Warn "Buộc dừng."
    & taskkill /PID $p /T /F | Out-Null
    if ((Cfg "EMBEDDED_PG") -match "^(true|1)$") { & $Py -m app.tools.embedded_pg stop 2>$null | Out-Null }
  }
  Remove-Item $PidFile, $StopFile -ErrorAction SilentlyContinue
  Info "Đã dừng."
}

function Do-Status {
  $p = Running-Pid
  if (-not $p) { Warn "Không chạy."; exit 1 }
  Info "Supervisor PID $p"
  if (-not (Healthy)) { Warn "API không phản hồi trên cổng $(Port)"; exit 1 }
  try {
    $m = Invoke-RestMethod "http://127.0.0.1:$(Port)/api/monitoring" -Headers (Auth) -TimeoutSec 20
    $h = $m.host
    Write-Host ("Trạng thái: {0}   CPU {1}%  RAM {2}% (trống {3} MB)  Đĩa trống {4} GB" -f $m.status.ToUpper(), $h.cpu_percent, $h.ram_percent, $h.ram_available_mb, $h.disk_free_gb)
    foreach ($w in $m.workers) { Write-Host ("  worker {0,-10} {1} {2}" -f $w.kind, $(if ($w.online) { "ON " } else { "OFF" }), $w.state) }
    foreach ($a in $m.alerts) { Write-Host ("  [{0}] {1}" -f $a.severity, $a.message) -ForegroundColor Yellow }
  } catch { Info "API OK (không đọc được /api/monitoring: $($_.Exception.Message))" }
}

switch ($Command.ToLower()) {
  "start"   { Do-Start }
  "run"     { Need-Venv; Set-Location (Join-Path $App "backend"); & $Py -m app.tools.supervisor }
  "stop"    { Do-Stop }
  "restart" { Do-Stop; Do-Start }
  "status"  { Do-Status }
  "logs"    { $f = Join-Path $App "logs\app.log"; if (Test-Path $f) { Get-Content $f -Tail 80 -Wait -Encoding UTF8 } else { Warn "Chưa có logs\app.log" } }
  "open"    { Start-Process "http://localhost:$(Port)" }
  "backup"  {
    Need-Venv; Set-Location (Join-Path $App "backend")
    $a = @("-m", "app.tools.backup", "create"); if ($DbOnly) { $a += "--db-only" }
    # the embedded database must be up to be dumped; start it if the app is stopped
    $own = $false
    if ((Cfg "EMBEDDED_PG") -match "^(true|1)$") { & $Py -m app.tools.embedded_pg start | Out-Null; $own = -not (Running-Pid) }
    & $Py @a
    if ($own) { & $Py -m app.tools.embedded_pg stop | Out-Null }
  }
  "restore" {
    Need-Venv
    if (-not $Arg) { Die "Cách dùng: coco restore <file.zip> [-WithEnv]" }
    $file = (Resolve-Path $Arg).Path
    Do-Stop
    Set-Location (Join-Path $App "backend")
    $a = @("-m", "app.tools.backup", "restore", $file); if ($WithEnv) { $a += "--with-env" }; if ($Yes) { $a += "--yes" }
    & $Py @a
    if ((Cfg "EMBEDDED_PG") -match "^(true|1)$") { & $Py -m app.tools.embedded_pg stop | Out-Null }
  }
  "autostart" {
    $name = "CocoAutomation"
    if ($Arg -eq "on") {
      $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$App\coco.cmd`" start" -WorkingDirectory $App
      $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
      $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
      Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
      Info "Đã bật: Coco tự chạy mỗi khi bạn đăng nhập Windows."
    } elseif ($Arg -eq "off") {
      Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
      Info "Đã tắt tự chạy."
    } else { Die "Cách dùng: coco autostart on|off" }
  }
  "firewall" {
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) { Die "Cần quyền Administrator: mở PowerShell bằng 'Run as administrator' rồi chạy lại 'coco firewall'." }
    New-NetFirewallRule -DisplayName "Coco Automation" -Direction Inbound -Protocol TCP -LocalPort (Port) -Profile Private -Action Allow -ErrorAction SilentlyContinue | Out-Null
    Info "Đã cho phép cổng $(Port) trên mạng Private (LAN nhà/văn phòng). Không mở cho mạng Public."
  }
  default {
    Get-Help $MyInvocation.MyCommand.Path | Out-Null
    Write-Host "Cách dùng: coco start | run | stop | restart | status | logs | open | backup [-DbOnly] | restore <file.zip> [-WithEnv] | autostart on|off | firewall"
  }
}

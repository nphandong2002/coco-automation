<#
  Cài đặt Coco Automation trên Windows 10/11 (không cần quyền Administrator).

    install-windows.cmd                       # nhấp đúp, hoặc:
    powershell -File scripts\windows\install.ps1 [-ExternalDb "postgresql+psycopg://user:pass@host:5432/db"]
                                               [-Port 8080] [-Autostart] [-SkipFrontend] [-Rebuild]

  Việc làm: tạo .venv + cài thư viện, tạo .env (SECRET_KEY, mật khẩu), tạo PostgreSQL riêng (hoặc dùng DB của bạn),
  chạy migration, build dashboard. Chạy lại an toàn (không ghi đè .env / dữ liệu).
#>
param(
  [string]$ExternalDb = "",
  [int]$Port = 8080,
  [switch]$Autostart,
  [switch]$SkipFrontend,
  [switch]$Rebuild
)
$ErrorActionPreference = "Stop"
$App = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $App
function Info($m) { Write-Host "[install] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[install] $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "[install] $m" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- 1. Python >= 3.10
Info "1/6 Kiểm tra Python..."
$py = $null
foreach ($cand in @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.10"), @("python"))) {
  try {
    $exe = $cand[0]; $args2 = @($cand | Select-Object -Skip 1)
    $v = & $exe @args2 -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.10") { $py = @($exe) + $args2; break }
  } catch { }
}
if (-not $py) {
  Die "Cần Python 3.10+ (khuyến nghị 3.12). Cài bằng:  winget install Python.Python.3.12  (nhớ tích 'Add python.exe to PATH') rồi chạy lại."
}
Info "Dùng: $($py -join ' ')"

# ---------------------------------------------------------------- 2. venv + packages
Info "2/6 Tạo môi trường Python (.venv) và cài thư viện (vài phút lần đầu)..."
$venvPy = Join-Path $App ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { & $py[0] @($py | Select-Object -Skip 1) -m venv (Join-Path $App ".venv"); if ($LASTEXITCODE) { Die "Không tạo được venv" } }
& $venvPy -m pip install --upgrade pip wheel --quiet
& $venvPy -m pip install -r backend\requirements.txt -r backend\requirements-windows.txt --quiet
if ($LASTEXITCODE) { Die "pip install thất bại" }

# ---------------------------------------------------------------- 3. .env
Info "3/6 Tạo cấu hình .env..."
Push-Location backend
try {
  $mk = @("-m", "app.tools.make_env", "--port", $Port)
  if ($ExternalDb) { $mk += @("--external-db", $ExternalDb) }
  & $venvPy @mk
  if ($LASTEXITCODE) { Die "Không tạo được .env" }

  # ------------------------------------------------------------ 4. database
  Info "4/6 Chuẩn bị database và migration..."
  $embedded = (Select-String -Path (Join-Path $App ".env") -Pattern "^EMBEDDED_PG=(true|1)" -Quiet)
  if ($embedded) {
    & $venvPy -m app.tools.embedded_pg ensure
    if ($LASTEXITCODE) { Die "Không khởi tạo được PostgreSQL riêng (xem logs\postgres.log)" }
  }
  & $venvPy -m alembic upgrade head
  if ($LASTEXITCODE) { Die "Migration thất bại" }
  if ($embedded) { & $venvPy -m app.tools.embedded_pg stop | Out-Null }   # supervisor sẽ tự bật lại
} finally { Pop-Location }

# ---------------------------------------------------------------- 5. frontend
Info "5/6 Build dashboard..."
if ($SkipFrontend) { Warn "Bỏ qua build dashboard (-SkipFrontend)." }
elseif ((Test-Path "frontend\dist\index.html") -and -not $Rebuild) {
  Info "Dùng dashboard đã build sẵn (frontend\dist). Thêm -Rebuild nếu muốn build lại."
} elseif (Get-Command node -ErrorAction SilentlyContinue) {
  Push-Location frontend
  try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE) { Die "npm ci thất bại" }
    npm run build
    if ($LASTEXITCODE) { Die "build dashboard thất bại" }
  } finally { Pop-Location }
} else {
  Die "Cần Node.js 18+ để build dashboard:  winget install OpenJS.NodeJS.LTS  rồi chạy lại (hoặc dùng gói đã build sẵn: make-package.ps1)."
}

foreach ($d in @("storage", "logs", "backups", "run", "data")) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

# ---------------------------------------------------------------- 6. autostart
if ($Autostart) { Info "6/6 Bật tự chạy khi đăng nhập Windows..."; & (Join-Path $PSScriptRoot "coco.ps1") autostart on }
else { Info "6/6 Bỏ qua tự chạy khi đăng nhập (bật sau bằng:  coco autostart on)." }

Write-Host ""
Info "Hoàn tất!  Khởi chạy:  coco start     (mở http://localhost:$Port)"
Info "Các lệnh:  coco start | stop | restart | status | logs | backup | restore | autostart | firewall"

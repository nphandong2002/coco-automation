<#
  Tạo gói cài đặt Windows: dist\coco-automation-windows.zip
  (mã nguồn + dashboard đã build sẵn => máy đích KHÔNG cần Node.js, chỉ cần Python 3.10+).
    powershell -File scripts\windows\make-package.ps1
#>
$ErrorActionPreference = "Stop"
$App = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $App
function Info($m) { Write-Host "[package] $m" -ForegroundColor Green }

if (-not (Test-Path "frontend\dist\index.html") -or ($args -contains "-Rebuild")) {
  Info "Build dashboard..."
  Push-Location frontend; npm ci --no-audit --no-fund; npm run build; Pop-Location
}
$stage = Join-Path $env:TEMP ("coco-pkg-" + [guid]::NewGuid().ToString("N"))
$root = Join-Path $stage "coco-automation"
New-Item -ItemType Directory -Force -Path $root | Out-Null
Info "Chép mã nguồn..."
$files = git ls-files
foreach ($f in $files) {
  if ($f -match '^(docs/schema\.sql)$') { }
  $dst = Join-Path $root $f
  New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
  Copy-Item $f $dst
}
Copy-Item "frontend\dist" (Join-Path $root "frontend\dist") -Recurse
New-Item -ItemType Directory -Force -Path "dist" | Out-Null
$zip = Join-Path $App "dist\coco-automation-windows.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [IO.Compression.CompressionLevel]::Optimal, $false)
Remove-Item $stage -Recurse -Force
Info ("Đã tạo {0} ({1:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB))
Info "Trên máy đích: giải nén -> nhấp đúp install-windows.cmd -> coco start"

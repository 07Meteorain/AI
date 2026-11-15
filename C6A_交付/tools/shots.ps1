# C6A · 看板截图脚本（UTF-8 with BOM，Windows PowerShell 5.1 才能正确读中文）
#
# 为什么用 Edge 无头模式而不是手工截图：
#   演示图必须是「当前代码真实渲染的结果」。这个脚本把 URL、窗口尺寸、主题、抽屉、
#   演示模式全部参数化（靠 app 的 hash 深链），重跑一次就能拿到与代码一致的一组图。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools/shots.ps1
#   powershell -ExecutionPolicy Bypass -File tools/shots.ps1 -Only 02,04

param(
  [string]$OutDir = "",
  [string]$Only = "",
  [string]$Edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)

$ErrorActionPreference = "Continue"  # Edge 会往 stderr 打账号头像的噪声，不能当致命错误
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $root "demo\截图" }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

$app = (Join-Path $root "app\index.html") -replace "\\", "/"
$base = "file:///$app"

# 名称、hash、宽、高
$shots = @(
  @("01-总览",            "#overview",                              1600, 1190),
  @("02-洞察",            "#insights",                              1600, 2200),
  @("03-学生表",          "#students",                              1600, 1490),
  @("04-学生详情",        "#students?open=2025285201112",           1600, 1120),
  @("05-口径",            "#dictionary",                            1600, 1880),
  @("06-真实数据",        "#real",                                  1600, 1580),
  @("07-浅色主题",        "#overview?theme=light",                  1600, 1190),
  @("08-演示模式",        "#overview?tour=1",                       1600, 1190),
  @("09-筛选联动-C6",     "#overview?c=C6",                         1600, 1190)
)

$want = @()
if ($Only) { $want = $Only.Split(",") | ForEach-Object { $_.Trim() } }

if (-not (Test-Path $Edge)) { throw "找不到 Edge：$Edge" }

foreach ($s in $shots) {
  $name = $s[0]; $hash = $s[1]; $w = $s[2]; $h = $s[3]
  if ($want.Count -and -not ($want | Where-Object { $name.StartsWith($_) })) { continue }

  $png = Join-Path $OutDir "$name.png"
  $profile = Join-Path $env:TEMP ("edge-c6a-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
  $url = "$base$hash"

  try { & $Edge --headless=new --disable-gpu --hide-scrollbars --no-first-run --no-default-browser-check `
    --disable-extensions --disable-background-networking `
    --user-data-dir="$profile" --window-size="$w,$h" --virtual-time-budget=6000 `
    --screenshot="$png" "$url" 2>$null | Out-Null } catch { }

  Start-Sleep -Milliseconds 700
  if (Test-Path $png) {
    $kb = [math]::Round((Get-Item $png).Length / 1KB, 1)
    Write-Output ("OK  {0,-16} {1,5} x {2,-5} {3,7} KB" -f $name, $w, $h, $kb)
  } else {
    Write-Output ("FAIL {0}  （检查 Edge 路径与 file:// 链接）" -f $name)
  }
  Remove-Item -Recurse -Force $profile -ErrorAction SilentlyContinue
}

Write-Output ""
Write-Output ("输出目录：{0}" -f $OutDir)
Get-ChildItem $OutDir -Filter *.png | Sort-Object Name | ForEach-Object { "  {0}  {1} KB" -f $_.Name, [math]::Round($_.Length / 1KB, 1) }

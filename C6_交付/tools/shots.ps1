# 生成 demo 截图（Windows / Edge 或 Chrome）。用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\shots.ps1
#   也可加参数：-Width 1600 -Height 1000
#
# 为什么要把 app 复制到 %TEMP% 再截图：
#  1) headless 浏览器对含中文的 file:// 路径传参会失败（实测 Edge 会直接不加载页面）；
#  2) 复制到 ASCII 临时目录能保证每次都是「干净 session」（localStorage 为空），
#     截图结果可复现，不受上一次浏览留下的草稿/版本影响。
param(
  [string]$Edge = "",
  [int]$Width = 1440,
  [int]$Height = 900
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $PSScriptRoot
$app = Join-Path $here "app"
$outDir = Join-Path $here "demo\截图"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

if (-not $Edge -or -not (Test-Path $Edge)) {
  $candidates = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
  )
  $Edge = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $Edge) { throw "找不到 Edge/Chrome，请用 -Edge 指定浏览器路径" }
}

$tmp = Join-Path $env:TEMP ("promptgate-shots-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
Copy-Item -Recurse $app $tmp
$base = "file:///" + ($tmp -replace '\\', '/') + "/index.html"
$logOut = Join-Path $env:TEMP "promptgate-shot-out.log"
$logErr = Join-Path $env:TEMP "promptgate-shot-err.log"

$shots = @(
  @{ name = "01-体检-反面教材"; query = "sample=bad&theme=dark"; w = $Width; h = $Height },
  @{ name = "02-体检-合格样例"; query = "sample=good&theme=dark"; w = $Width; h = $Height },
  @{ name = "03-预算"; query = "sample=good&theme=dark&tab=budget"; w = $Width; h = $Height },
  @{ name = "04-规则表"; query = "sample=good&theme=dark&tab=rules"; w = $Width; h = $Height },
  @{ name = "05-注入面未隔离"; query = "sample=injection&theme=dark&filter=error"; w = $Width; h = $Height },
  @{ name = "06-浅色主题"; query = "sample=good&theme=light"; w = $Width; h = $Height },
  @{ name = "07-窄屏"; query = "sample=bad&theme=dark"; w = 474; h = 880 }
)

$i = 0
foreach ($shot in $shots) {
  $i++
  $png = Join-Path $env:TEMP ("pg-shot-" + $i + ".png")
  if (Test-Path $png) { Remove-Item $png -Force }
  $url = $base + "?" + $shot.query

  $argv = @(
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--force-device-scale-factor=1",
    ("--window-size=" + $shot.w + "," + $shot.h),
    "--virtual-time-budget=5000",
    ("--screenshot=" + $png),
    $url
  )
  $proc = Start-Process -FilePath $Edge -ArgumentList $argv -Wait -PassThru `
    -RedirectStandardOutput $logOut -RedirectStandardError $logErr -WindowStyle Hidden

  for ($n = 0; $n -lt 80; $n++) {
    if (Test-Path $png) { break }
    Start-Sleep -Milliseconds 100
  }
  if (-not (Test-Path $png)) { throw ("截图失败: " + $shot.name + "（退出码 " + $proc.ExitCode + "，日志见 " + $logErr + "）") }

  $target = Join-Path $outDir ($shot.name + ".png")
  Move-Item -Force $png $target
  Write-Host ("OK  " + $shot.name + ".png")
}

Remove-Item -Recurse -Force $tmp
Write-Host ("`n共 " + $shots.Count + " 张，输出目录: " + $outDir)

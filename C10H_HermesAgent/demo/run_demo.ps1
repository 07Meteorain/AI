# C10H demo 复跑脚本
# 用法:
#   .\run_demo.ps1                 # 跑全部场景
#   .\run_demo.ps1 -Scenario 01    # 只跑场景 01
# 前置:
#   $env:HERMES_HOME='E:\hermes'
#   Ollama 已启动，且存在 gemma4-e2b-64k
#   hermes gateway run 已在运行

[CmdletBinding()]
param(
    [ValidateSet('01', '02', '03', '04', 'all')]
    [string]$Scenario = 'all',
    [string]$HermesHome = 'E:\hermes'
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Prompts = Join-Path $Root 'prompts'
$Transcripts = Join-Path $Root 'transcripts'
New-Item -ItemType Directory -Force -Path $Transcripts | Out-Null

$Hermes = Join-Path $HermesHome 'bin\hermes.exe'
if (-not (Test-Path $Hermes)) { throw "找不到 $Hermes；请确认 -HermesHome" }
$env:HERMES_HOME = $HermesHome

# 场景表：编号 -> prompt / toolsets
$Scenarios = [ordered]@{
    '01' = @{ Prompt = '01_summary.md';        Tools = 'file,terminal' }
    '02' = @{ Prompt = '02_memory_write.md';   Tools = 'memory,terminal,file' }
    '03' = @{ Prompt = '03_memory_read.md';    Tools = 'file' }
    '04' = @{ Prompt = '04_skill.md';          Tools = 'skills,terminal,file' }
}

# 1) 模型检查
try {
    $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
    if (-not ($tags.models.name -contains 'gemma4-e2b-64k:latest')) {
        Write-Warning 'Ollama 中没有 gemma4-e2b-64k，请先执行:'
        Write-Warning '  ollama create gemma4-e2b-64k -f ..\配置说明\配置模板\Modelfile'
    }
} catch {
    throw "连不上 Ollama (127.0.0.1:11434)。先运行: ollama serve"
}

# 2) 网关检查
& $Hermes gateway status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Warning '网关未运行，尝试在后台启动...'
    Start-Process -FilePath $Hermes -ArgumentList 'gateway', 'run' -WindowStyle Hidden
    Start-Sleep -Seconds 8
    & $Hermes gateway status
    if ($LASTEXITCODE -ne 0) { throw '网关启动失败；请手动运行 hermes gateway run' }
}

# 3) 逐个跑
$ids = if ($Scenario -eq 'all') { $Scenarios.Keys } else { @($Scenario) }
foreach ($id in $ids) {
    $cfg = $Scenarios[$id]
    $prompt = Join-Path $Prompts $cfg.Prompt
    $jsonl = Join-Path $Transcripts "$($cfg.Prompt -replace '\.md$', '').jsonl"
    $md = Join-Path $Transcripts "$($cfg.Prompt -replace '\.md$', '').md"
    Write-Host "`n=== 场景 $id : $($cfg.Prompt) ===" -ForegroundColor Cyan

    Push-Location (Join-Path $Root 'workspace')
    try {
        $chatArgs = @('chat', '--query-file', $prompt, '-t', $cfg.Tools, '--format', 'stream-json')
        $proc = Start-Process -FilePath $Hermes -ArgumentList $chatArgs -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput $jsonl -RedirectStandardError "$jsonl.err"
        Write-Host ("exit_code={0}，轨迹: {1}" -f $proc.ExitCode, $jsonl)
    } finally {
        Pop-Location
    }

    python (Join-Path $Root 'tools\render_transcript.py') $jsonl $md
    if (Test-Path $md) { Write-Host ("可读版: {0}" -f $md) }
}

Write-Host "`n全部完成。先看 transcripts\01_summary.md。" -ForegroundColor Green

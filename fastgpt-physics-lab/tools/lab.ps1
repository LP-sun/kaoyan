# ---------------------------------------------------------------------------
# lab.ps1 — fastgpt-physics-lab 的启动 / 停止 / 状态 / 健康 / 备份
#
# 为什么是 PowerShell 而不是 bash：
#   本机 `bash` 实际是 WSL 的 bash，而当前用户对 WSL 没有访问权限
#   （实测 `wsl -l -q` 与直接调 bash 均为 E_ACCESSDENIED / execvpe 失败）。
#   因此运维脚本必须用 PowerShell 才真正可执行。
#   scripts/lab-ctl.sh 仍保留作为参考（在能跑 bash 的机器上可用）。
#
# ⚠ 安全约定（本脚本严格遵守）：
#   - 只操作 Compose 项目 `fastgpt-physics-lab`（docker-compose.yml 顶层已用 name: 固定）
#   - 不做 docker system prune / docker volume prune
#   - 不停止/删除其它项目的容器、卷或网络
#   - down 不删除数据卷
#
# 用法：
#   powershell -File tools\lab.ps1 up
#   powershell -File tools\lab.ps1 down
#   powershell -File tools\lab.ps1 status
#   powershell -File tools\lab.ps1 health
#   powershell -File tools\lab.ps1 logs
#   powershell -File tools\lab.ps1 backup
# ---------------------------------------------------------------------------
param(
  [Parameter(Position = 0)]
  [ValidateSet('up', 'down', 'status', 'health', 'logs', 'backup', 'help')]
  [string]$Action = 'help'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot   # tools/ 的上级 = 项目根
Set-Location $Root

$Project = 'fastgpt-physics-lab'
$EnvFile = 'env/.env'
$Compose = @('compose', '--project-name', $Project, '--env-file', $EnvFile)

# --- 确保能找到 docker.exe（Windows 上 Docker CLI 可能不在当前 PATH）---------
function Resolve-Docker {
  $cmd = Get-Command docker -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $candidates = @(
    'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
    "$env:LOCALAPPDATA\Docker\resources\bin\docker.exe"
  )
  foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
  throw "找不到 docker.exe。请确认 Docker Desktop 已安装并已启动。"
}
$Docker = Resolve-Docker
$DockerDir = Split-Path -Parent $Docker
$env:PATH = "$DockerDir;$env:PATH"

function Invoke-Compose {
  param([string[]]$Args, [switch]$Quiet)
  # 用 & 直接调用，避免 cmd 的引号问题
  $all = $Compose + $Args
  if ($Quiet) { & $Docker @all 2>&1 | Out-Null }
  else { & $Docker @all 2>&1 | ForEach-Object { "  $_" } }
  return $LASTEXITCODE
}

function Require-Env {
  if (-not (Test-Path $EnvFile)) {
    throw "缺少 $EnvFile。请先执行：Copy-Item env\.env.example env\.env 并填入密钥。"
  }
}

function Get-EnvValue {
  param([string]$Key)
  $line = Get-Content $EnvFile -Encoding UTF8 |
    Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
  if (-not $line) { return '' }
  return ($line -replace "^$Key=", '')
}

switch ($Action) {

  'up' {
    Require-Env
    Write-Output "启动 $Project ..."
    Invoke-Compose @('up', '-d') | Out-Null
    Write-Output ''
    Invoke-Compose @('ps') | Out-Null
  }

  'down' {
    Require-Env
    Write-Output "停止 $Project（不加 -v，数据卷保留，不删除任何数据）..."
    Invoke-Compose @('down') | Out-Null
    Write-Output "已停止。数据卷仍保留，下次 up 会复用。"
  }

  'status' {
    Require-Env
    Invoke-Compose @('ps') | Out-Null
  }

  'health' {
    Require-Env
    $names = & $Docker @Compose ps --format '{{.Name}}' 2>&1
    Write-Output ('{0,-52} {1}' -f '容器', '状态')
    Write-Output ('-' * 72)
    foreach ($n in $names) {
      if (-not $n) { continue }
      $st = (& $Docker inspect $n --format '{{.State.Status}}{{if .State.Health}} / {{.State.Health.Status}}{{end}}' 2>&1) -join ''
      Write-Output ('{0,-52} {1}' -f $n, $st)
    }
    Write-Output ''
    Write-Output '端口暴露检查（本项目必须只监听 127.0.0.1）：'
    $rows = netstat -ano | Select-String 'LISTENING' |
      Where-Object { $_ -match ':(3100|3101|3102)\s' }
    if (-not $rows) { Write-Output '  (未发现本项目端口在监听)' }
    foreach ($r in $rows) {
      $local = (($r -replace '\s+', ' ').Trim().Split(' '))[1]
      $tag = if ($local -like '127.0.0.1:*') { '仅回环 OK' } else { '⚠ 对外暴露' }
      Write-Output ('  {0,-22} {1}' -f $local, $tag)
    }
  }

  'logs' {
    Require-Env
    Invoke-Compose @('logs', '-f', '--tail', '100') | Out-Null
  }

  'backup' {
    Require-Env
    $ts = Get-Date -Format 'yyyyMMdd-HHmmss'
    $out = Join-Path $Root "backups\$ts"
    New-Item -ItemType Directory -Force -Path $out | Out-Null

    $mu = Get-EnvValue 'MONGO_ROOT_USERNAME'
    $mp = Get-EnvValue 'MONGO_ROOT_PASSWORD'

    Write-Output "备份 MongoDB -> $out\fastgpt-mongo.archive"
    # mongodump 输出到 stdout，由 PowerShell 重定向到文件
    $archive = Join-Path $out 'fastgpt-mongo.archive'
    & $Docker exec 'fastgpt-physics-lab-fastgpt-mongo-1' `
        mongodump -u $mu -p $mp --authenticationDatabase admin `
        --db fastgpt --archive --gzip > $archive 2>$null
    if ((Get-Item $archive -ErrorAction SilentlyContinue).Length -gt 0) {
      Write-Output ("  完成，{0:N0} 字节" -f (Get-Item $archive).Length)
    } else {
      Write-Output '  ⚠ 归档为空，请手动检查 mongo 容器是否在运行'
    }

    Write-Output '备份 MinIO 数据（本项目专属卷，只读挂载）...'
    $minioTar = Join-Path $out 'minio-data.tar.gz'
    & $Docker run --rm `
        -v "${Project}_fastgpt-minio:/data:ro" `
        -v "${out}:/backup" `
        alpine:3 tar czf /backup/minio-data.tar.gz -C /data . 2>$null
    if (Test-Path $minioTar) { Write-Output '  完成' }
    else { Write-Output '  (跳过：本地无 alpine 镜像或拉取失败，可稍后重试)' }

    Copy-Item $EnvFile (Join-Path $out '.env') -Force
    Write-Output ''
    Write-Output "备份完成：$out"
    Get-ChildItem $out | ForEach-Object { Write-Output ("  {0,-28} {1:N0} 字节" -f $_.Name, $_.Length) }
    Write-Output ''
    Write-Output '⚠ 该目录含数据库与密钥，不要上传到任何公开位置。'
  }

  default {
    Get-Content $PSCommandPath | Select-Object -Skip 1 -First 25 | ForEach-Object { $_ -replace '^# ?', '' }
  }
}

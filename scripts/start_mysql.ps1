<#
.SYNOPSIS
    启动免安装版 MySQL（前台常驻，窗口关掉即停止）。

.DESCRIPTION
    init_mysql.ps1 负责一次性初始化；本脚本用于日常开发时启动数据库。
    在一个单独的 PowerShell 窗口里运行它，保持窗口打开即可。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start_mysql.ps1
#>
[CmdletBinding()]
param(
    [string]$RuntimeLink = 'D:\smart-menu-rt',
    [int]$Port = 3306,
    [string]$MySqlVersionDir = 'mysql-8.0.28-winx64'
)

$ErrorActionPreference = 'Stop'

# MySQL 不支持中文路径，必须通过英文入口访问
if (-not (Test-Path $RuntimeLink)) {
    throw "找不到英文路径入口 $RuntimeLink，请先执行 scripts\init_mysql.ps1"
}

$MySqlHome = Join-Path $RuntimeLink $MySqlVersionDir
$DataDir   = Join-Path $RuntimeLink 'mysql-data'
$TmpDir    = Join-Path $RuntimeLink 'tmp'
$Mysqld    = Join-Path $MySqlHome 'bin\mysqld.exe'

foreach ($p in @($Mysqld, $DataDir)) {
    if (-not (Test-Path $p)) { throw "缺少必需路径：$p（请先执行 scripts\init_mysql.ps1）" }
}
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

if (@(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue).Count -gt 0) {
    Write-Host "端口 $Port 已被占用，MySQL 可能已在运行。" -ForegroundColor Yellow
    exit 0
}

Write-Host "MySQL 启动中，监听 127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 停止；关闭本窗口即结束数据库。" -ForegroundColor Cyan
Write-Host ''

# 前台运行，日志直接打印在当前窗口
& $Mysqld `
    "--basedir=$MySqlHome" `
    "--datadir=$DataDir" `
    "--tmpdir=$TmpDir" `
    "--port=$Port" `
    --character-set-server=utf8mb4 `
    --collation-server=utf8mb4_unicode_ci `
    --default-authentication-plugin=mysql_native_password `
    --console
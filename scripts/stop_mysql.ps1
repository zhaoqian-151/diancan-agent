<#
.SYNOPSIS
    停止免安装版 MySQL。

.DESCRIPTION
    优先用 mysqladmin shutdown 正常关闭（会刷盘、写日志）；
    如果连不上则停止并提示，不结束其他 MySQL 实例。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\stop_mysql.ps1
#>
[CmdletBinding()]
param(
    [string]$RuntimeLink = 'D:\smart-menu-rt',
    [int]$Port = 3306,
    [string]$RootPassword = 'root',
    [string]$MySqlVersionDir = 'mysql-8.0.28-winx64'
)

$ErrorActionPreference = 'Stop'

$MySqlAdmin = Join-Path $RuntimeLink "$MySqlVersionDir\bin\mysqladmin.exe"

if (-not (Test-Path $MySqlAdmin)) {
    throw "mysqladmin was not found. No MySQL process was stopped."
} else {
    Write-Host '正在通过 mysqladmin 正常关闭 ...'
    & $MySqlAdmin -u root "-p$RootPassword" --host=127.0.0.1 "--port=$Port" shutdown 2>&1 |
        Where-Object { $_ -notmatch 'Using a password on the command line' } |
        ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE -ne 0) { throw "MySQL shutdown failed on port $Port. No other instance was stopped." }
}

Start-Sleep -Seconds 3
$remain = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue).Count
if ($remain -eq 0) {
    Write-Host 'MySQL 已停止。' -ForegroundColor Green
} else {
    throw "Port $Port is still listening. No process was force-stopped."
}

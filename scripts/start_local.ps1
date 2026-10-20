<# Start the configured database, API and UI; reuse healthy running services. #>
[CmdletBinding()]
param(
    [string]$RuntimeLink = 'D:\smart-menu-rt'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logRoot = Join-Path $projectRoot 'logs'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project Python is missing. Install the project dependencies first.' }
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

Push-Location $projectRoot
try {
    $rawConfig = & $pythonPath -c 'import json; from tools import config; print(json.dumps(dict(mysql_host=config.MYSQL_HOST, mysql_port=config.MYSQL_PORT, api_port=config.SERVER_PORT)))'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read project configuration.' }
    $settings = $rawConfig | ConvertFrom-Json

    function Test-TcpPort([string]$TargetHost, [int]$TargetPort) {
        $client = New-Object System.Net.Sockets.TcpClient
        try { return $client.ConnectAsync($TargetHost, $TargetPort).Wait(1000) -and $client.Connected }
        catch { return $false }
        finally { $client.Dispose() }
    }
    function Read-Health([string]$Url) {
        try {
            # Windows PowerShell 5 may decode JSON without a charset as ANSI.
            # The API returns UTF-8 paths, including the Chinese workspace name.
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing
            $response.RawContentStream.Position = 0
            $reader = New-Object System.IO.StreamReader($response.RawContentStream, [Text.Encoding]::UTF8)
            try { return ($reader.ReadToEnd() | ConvertFrom-Json) }
            finally { $reader.Dispose() }
        }
        catch { return $null }
    }
    function Wait-Ready([scriptblock]$Probe, [string]$ServiceName, [int]$Seconds = 30) {
        $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
        do {
            if (& $Probe) { return }
            Start-Sleep -Milliseconds 500
        } while ([DateTime]::UtcNow -lt $deadline)
        throw "$ServiceName did not become ready. Check $logRoot."
    }
    function Assert-ProjectApi($Health) {
        if (-not $Health -or -not $Health.config_file -or [IO.Path]::GetFullPath($Health.config_file) -ne (Join-Path $projectRoot '.env')) {
            throw "API port $($settings.api_port) is occupied by a different service. No existing process was stopped."
        }
    }

    if (-not (Test-TcpPort $settings.mysql_host $settings.mysql_port)) {
        if ($settings.mysql_host -notin @('127.0.0.1', 'localhost', '::1')) { throw 'Configured remote database is unavailable. Start that database first.' }
        $mysqlHome = Join-Path $RuntimeLink 'mysql-8.0.28-winx64'
        $mysqlExe = Join-Path $mysqlHome 'bin\mysqld.exe'
        $dataRoot = Join-Path $RuntimeLink 'mysql-data'
        $tmpRoot = Join-Path $RuntimeLink 'tmp'
        if (-not (Test-Path -LiteralPath $mysqlExe) -or -not (Test-Path -LiteralPath $dataRoot)) {
            throw 'Existing MySQL installation/data was not found. This script never initializes or overwrites a database.'
        }
        New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null
        $mysqlArgs = @("--basedir=`"$mysqlHome`"", "--datadir=`"$dataRoot`"", "--tmpdir=`"$tmpRoot`"", "--port=$($settings.mysql_port)", '--character-set-server=utf8mb4', '--collation-server=utf8mb4_unicode_ci', '--default-authentication-plugin=mysql_native_password', '--console')
        $null = Start-Process -FilePath $mysqlExe -ArgumentList $mysqlArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'local-mysql.log') -RedirectStandardError (Join-Path $logRoot 'local-mysql.err.log') -PassThru
        Wait-Ready { Test-TcpPort $settings.mysql_host $settings.mysql_port } 'MySQL'
    }
    Write-Host "MySQL reachable: $($settings.mysql_host):$($settings.mysql_port)"

    $apiBase = "http://127.0.0.1:$($settings.api_port)"
    if (Test-TcpPort '127.0.0.1' $settings.api_port) {
        Assert-ProjectApi (Read-Health "$apiBase/health")
    } else {
        $null = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','api.main:app','--host','127.0.0.1','--port',"$($settings.api_port)") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'local-api.log') -RedirectStandardError (Join-Path $logRoot 'local-api.err.log') -PassThru
    }
    Wait-Ready { $health = Read-Health "$apiBase/health"; $health -and $health.status -eq 'ok' -and $health.checks.mysql.ok } 'API and database connection'
    Assert-ProjectApi (Read-Health "$apiBase/health")
    Write-Host "API and database healthy: $apiBase"

    $uiRoot = Join-Path $projectRoot 'ui'
    $vitePath = Join-Path $uiRoot 'node_modules\vite\bin\vite.js'
    if (-not (Test-Path -LiteralPath $vitePath)) { throw 'Frontend dependencies missing. Run npm --prefix ui install first.' }
    if (-not (Test-TcpPort '127.0.0.1' 3000)) {
        $nodePath = (Get-Command node.exe).Source
        $null = Start-Process -FilePath $nodePath -ArgumentList @("`"$vitePath`"",'--host','127.0.0.1','--port','3000','--strictPort') -WorkingDirectory $uiRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'local-ui.log') -RedirectStandardError (Join-Path $logRoot 'local-ui.err.log') -PassThru
    }
    Wait-Ready { $health = Read-Health 'http://127.0.0.1:3000/api/health'; $health -and $health.status -eq 'ok' -and $health.checks.mysql.ok } 'Frontend API proxy'
    Assert-ProjectApi (Read-Health 'http://127.0.0.1:3000/api/health')
    Write-Host 'Ready: http://127.0.0.1:3000/   Admin: http://127.0.0.1:3000/admin'
} finally {
    Pop-Location
}

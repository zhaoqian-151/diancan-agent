<#
.SYNOPSIS
    一键初始化「免安装版 MySQL 8.0」并导入菜单数据。

.DESCRIPTION
    适用于没有管理员权限、无法使用 Docker 或 MySQL 安装包的场景。

    重要：MySQL 8.0 无法处理含中文的路径。项目所在路径
    （...\智能点餐agent\...）含中文，直接启动会把路径截断导致失败，
    因此在纯英文路径下建立一个目录入口（junction）指向项目里的
    _runtime 目录，所有 MySQL 参数都走这个英文路径。

    依次完成：解压 → 建英文入口 → 初始化数据目录 → 启动 → 建库 → 导入 menu.sql。
    可重复执行，已完成的步骤会自动跳过。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\init_mysql.ps1
#>
[CmdletBinding()]
param(
    [string]$ZipPath,
    [string]$RuntimeRoot,
    [string]$RuntimeLink = 'D:\smart-menu-rt',
    [string]$MySqlSqlPath,
    [int]$Port = 3306,
    [string]$RootPassword = 'root',
    [string]$Database = 'menu',
    [string]$MySqlVersionDir = 'mysql-8.0.28-winx64'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot   = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot

if (-not $ZipPath)       { $ZipPath       = Join-Path $WorkspaceRoot '_downloads\mysql-8.0.28-winx64.zip' }
if (-not $RuntimeRoot)   { $RuntimeRoot   = Join-Path $WorkspaceRoot '_runtime' }
if (-not $MySqlSqlPath)  { $MySqlSqlPath  = Join-Path $ProjectRoot 'database\schema.sql' }

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# mysqld/mysql 的 stderr 日志会被 'Stop' 当成终止性错误，这里改为按退出码判断
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$StdinText
    )
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($PSBoundParameters.ContainsKey('StdinText')) {
            $lines = $StdinText | & $FilePath @Arguments 2>&1 | ForEach-Object { "$_" }
        } else {
            $lines = & $FilePath @Arguments 2>&1 | ForEach-Object { "$_" }
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
    }
    [pscustomobject]@{ ExitCode = $code; Lines = @($lines) }
}

function Test-Port($p) {
    return @(Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue).Count -gt 0
}

# ---------------------------------------------------------------- 前置检查
Write-Step '前置检查'
if (-not (Test-Path $ZipPath))      { throw "找不到 MySQL ZIP：$ZipPath" }
if (-not (Test-Path $MySqlSqlPath)) { throw "找不到菜单脚本：$MySqlSqlPath" }
Write-Host ("  {0} ({1:N1} MB)" -f $ZipPath, ((Get-Item $ZipPath).Length / 1MB))

# ---------------------------------------------------------------- 1. 解压
Write-Step '1. 解压 MySQL'
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
if (Test-Path (Join-Path $RuntimeRoot "$MySqlVersionDir\bin\mysqld.exe")) {
    Write-Host '  已解压，跳过'
} else {
    Write-Host "  解压到 $RuntimeRoot ..."
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $RuntimeRoot)
    Write-Host '  解压完成'
}

# ---------------------------------------------------------------- 2. 英文路径入口
Write-Step '2. 建立英文路径入口（MySQL 不支持中文路径）'
Write-Host "  $RuntimeLink  ->  $RuntimeRoot"
if (Test-Path -LiteralPath $RuntimeLink) {
    $existingLink = Get-Item -LiteralPath $RuntimeLink
    $expectedTarget = [IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\')
    if ($existingLink.LinkType -ne 'Junction' -or [IO.Path]::GetFullPath([string]$existingLink.Target).TrimEnd('\') -ne $expectedTarget) {
        throw "Existing runtime entry points elsewhere: $RuntimeLink. No directory was changed."
    }
    $mk = 'Existing matching junction reused'
} else {
    $mk = New-Item -ItemType Junction -Path $RuntimeLink -Target $RuntimeRoot
}
if (-not (Test-Path $RuntimeLink)) { throw "创建目录入口失败：$mk" }
Write-Host "  已建立：$mk"

$MySqlHome = Join-Path $RuntimeLink $MySqlVersionDir
$DataDir   = Join-Path $RuntimeLink 'mysql-data'
$TmpDir    = Join-Path $RuntimeLink 'tmp'
$Mysqld    = Join-Path $MySqlHome 'bin\mysqld.exe'
$Mysql     = Join-Path $MySqlHome 'bin\mysql.exe'
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

# ---------------------------------------------------------------- 3. 初始化数据目录
Write-Step '3. 初始化数据目录'
if (Test-Path (Join-Path $DataDir 'mysql')) {
    Write-Host '  已初始化，跳过'
} else {
    if ((Test-Path -LiteralPath $DataDir) -and @(Get-ChildItem -LiteralPath $DataDir -Force).Count) {
        throw "Data directory is not empty. Refusing to remove existing files: $DataDir"
    }
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    Write-Host '  执行 mysqld --initialize-insecure ...'
    $r = Invoke-Native -FilePath $Mysqld -Arguments @(
        '--initialize-insecure', "--basedir=$MySqlHome", "--datadir=$DataDir", '--console')
    $r.Lines | Select-Object -Last 6 | ForEach-Object { Write-Host "    $_" }
    if ($r.ExitCode -ne 0) { throw "初始化失败，退出码 $($r.ExitCode)" }
    if (-not (Test-Path (Join-Path $DataDir 'mysql'))) { throw '初始化失败：未生成 mysql 系统库' }
    Write-Host '  初始化完成'
}

# ---------------------------------------------------------------- 4. 启动
Write-Step '4. 启动 mysqld'
if (Test-Port $Port) {
    Write-Host "  端口 $Port 已在监听，跳过"
} else {
    Start-Process -FilePath $Mysqld -ArgumentList @(
        "--basedir=$MySqlHome", "--datadir=$DataDir", "--tmpdir=$TmpDir", "--port=$Port",
        '--character-set-server=utf8mb4', '--collation-server=utf8mb4_unicode_ci',
        '--default-authentication-plugin=mysql_native_password',
        "--log-error=$DataDir\mysqld.err"
    ) -WindowStyle Hidden
    Write-Host "  已启动，等待端口 $Port ..."
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Seconds 2; if (Test-Port $Port) { $ok = $true; break } }
    if (-not $ok) {
        if (Test-Path "$DataDir\mysqld.err") { Get-Content "$DataDir\mysqld.err" -Tail 15 | ForEach-Object { Write-Host "    $_" } }
        throw "端口 $Port 未监听，请查看 $DataDir\mysqld.err"
    }
    Write-Host "  端口 $Port 已监听"
}

# ---------------------------------------------------------------- 5. 建库 + 导入
Write-Step '5. 设置密码、建库、导入 menu.sql'
$bootstrap = @"
ALTER USER 'root'@'localhost' IDENTIFIED BY '$RootPassword';
CREATE DATABASE IF NOT EXISTS ``$Database`` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
FLUSH PRIVILEGES;
"@
$r = Invoke-Native -FilePath $Mysql -Arguments @('-u', 'root', '--host=127.0.0.1', "--port=$Port") -StdinText $bootstrap
$r.Lines | ForEach-Object { Write-Host "  $_" }

$r = Invoke-Native -FilePath $Mysql -Arguments @(
    '-u', 'root', "-p$RootPassword", '--host=127.0.0.1', "--port=$Port",
    '--default-character-set=utf8mb4', $Database
) -StdinText (Get-Content $MySqlSqlPath -Raw -Encoding UTF8)
$r.Lines | Where-Object { $_ -notmatch 'Using a password on the command line' } | ForEach-Object { Write-Host "  $_" }
if ($r.ExitCode -ne 0) { throw "导入失败，退出码 $($r.ExitCode)" }

# ---------------------------------------------------------------- 6. 验证
Write-Step '6. 验证'
$r = Invoke-Native -FilePath $Mysql -Arguments @(
    '-u', 'root', "-p$RootPassword", '--host=127.0.0.1', "--port=$Port",
    '--default-character-set=utf8mb4', $Database
) -StdinText 'SELECT id, dish_name, price, category, spice_level FROM menu_items ORDER BY id;'
$r.Lines | Where-Object { $_ -notmatch 'Using a password on the command line' } | ForEach-Object { Write-Host "  $_" }

Write-Host "`n完成。MySQL 127.0.0.1:$Port / 库 $Database / 账号 root" -ForegroundColor Green
Write-Host '注意：日常开发请用 scripts\start_mysql.ps1 在一个单独窗口里常驻运行 mysqld。' -ForegroundColor Yellow

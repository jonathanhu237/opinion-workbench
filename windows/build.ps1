[CmdletBinding()]
param(
    [switch]$InstallTools,
    [switch]$PackageToolkit,
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:BuildRoot = Join-Path $PSScriptRoot "build"
$script:LogRoot = Join-Path $script:BuildRoot "logs"
New-Item -ItemType Directory -Force -Path $script:LogRoot | Out-Null
$script:LogPath = Join-Path $script:LogRoot ("build-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

function Write-Step([string]$Message) {
    Write-Host "`n== $Message ==" -ForegroundColor Cyan
}

function Invoke-Tool([string]$File, [string[]]$Arguments, [string]$WorkingDirectory = $script:RepoRoot) {
    Push-Location $WorkingDirectory
    try {
        & $File @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "命令失败（退出码 $LASTEXITCODE）：$File $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Has-Tool([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Refresh-ProcessPath {
    # winget installers update the user/machine environment for future
    # processes, while this PowerShell process keeps its original PATH.  Read
    # both scopes back before the tool checks so a successful installation can
    # be used without asking the maintainer to open a second shell.
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $misePaths = @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".local\share\mise\shims"),
        (Join-Path $env:LOCALAPPDATA "mise\bin")
    )
    $pathEntries = @($machinePath, $userPath) + $misePaths + @($env:Path)
    $env:Path = ($pathEntries |
        Where-Object { $_ } |
        Select-Object -Unique) -join ";"
}

function Find-InnoCompiler {
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    foreach ($candidate in @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )) {
        if ($candidate -and (Test-Path $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    foreach ($key in @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\ISCC.exe"
    )) {
        try {
            $value = (Get-ItemProperty -Path $key -Name "(default)" -ErrorAction Stop)."(default)"
            if ($value -and (Test-Path $value -PathType Leaf)) { return $value }
        }
        catch { }
    }
    return $null
}

function Install-OptionalTools {
    $packages = @(
        @{ Id = "jdx.mise"; Name = "mise" },
        @{ Id = "JRSoftware.InnoSetup"; Name = "Inno Setup" }
    )

    # ``build.cmd`` enables this switch by default.  A maintainer may already
    # have both tools installed while using a Windows edition without App
    # Installer/winget, so only require winget when there is an actual package
    # to install.
    $missing = @(
        if (-not (Has-Tool "mise")) { $packages[0] }
        if ($Installer -and -not (Find-InnoCompiler)) { $packages[1] }
    )
    if ($missing.Count -eq 0) { return }
    if (-not (Has-Tool "winget")) {
        $names = ($missing | ForEach-Object { $_.Name }) -join ", "
        throw "缺少 winget，无法安装：$names。请从 Microsoft Store 安装 App Installer，或手动安装构建工具后重试。"
    }
    foreach ($package in $missing) {
        Write-Step "安装 $($package.Name)"
        Invoke-Tool "winget" @(
            "install", "--exact", "--id", $package.Id,
            "--accept-source-agreements", "--accept-package-agreements"
        )
    }
    Refresh-ProcessPath
}

function Assert-Environment {
    Write-Step "检查 Windows 架构和工具"
    if ($env:OS -ne "Windows_NT") {
        throw "此入口必须在 Windows PowerShell 中运行。"
    }
    $architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITECTURE")
    $emulatedArchitecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITEW6432")
    if ($architecture -ne "AMD64" -and $emulatedArchitecture -ne "AMD64") {
        throw "当前版本只支持 Windows x64（检测到 $architecture）。"
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "当前版本只支持 Windows x64。"
    }
    if ([Environment]::OSVersion.Version.Major -lt 10) {
        throw "当前版本只支持 Windows 10 或更新版本。"
    }
    if ($InstallTools) {
        Install-OptionalTools
        Refresh-ProcessPath
    }
    if (-not (Has-Tool "mise")) {
        throw "缺少 mise。请重新运行 build.cmd，或从 https://mise.jdx.dev/ 安装 mise 后重试。"
    }
    Write-Step "准备 mise 锁定工具链"
    Invoke-Tool "mise" @("install") $script:RepoRoot
    if ($Installer -and $null -eq (Find-InnoCompiler)) {
        throw "缺少 Inno Setup 编译器 ISCC.exe。重新运行时加 -InstallTools，或手动安装 Inno Setup。"
    }
}

function Reset-BuildOutputs {
    Write-Step "清理可重试的构建产物"
    foreach ($path in @(
        (Join-Path $script:BuildRoot "app"),
        (Join-Path $script:BuildRoot "pyinstaller"),
        (Join-Path $script:RepoRoot "dist\windows\OpinionWorkbench-Setup.exe"),
        (Join-Path $script:RepoRoot "dist\windows\OpinionWorkbench-Windows.zip")
    )) {
        if (Test-Path $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $script:RepoRoot "dist\windows") | Out-Null
}

function Assert-CleanInputs {
    Write-Step "检查构建输入不含运行时资料"
    $forbidden = @(
        (Join-Path $script:RepoRoot "runtime"),
        (Join-Path $script:RepoRoot ".env"),
        (Join-Path $script:RepoRoot ".env.local")
    )
    foreach ($path in $forbidden) {
        if (Test-Path $path) {
            Write-Host "忽略构建机已有的运行时路径：$path" -ForegroundColor DarkYellow
        }
    }
    $allowedTemplates = @(
        (Join-Path $script:RepoRoot "frontend\.env.example"),
        (Join-Path $script:RepoRoot "backend\.env.example")
    )
    $runtimeRoot = Join-Path $script:RepoRoot "runtime"
    $sensitive = Get-ChildItem -Path $script:RepoRoot -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -notlike "$script:RepoRoot\.git\*" -and
            $_.FullName -notlike "$runtimeRoot\*" -and
            ($_.Name -like "*.key" -or $_.Name -like "*.sqlite3" -or
                ($_.Name -like ".env*" -and $allowedTemplates -notcontains $_.FullName))
        }
    if ($sensitive.Count -gt 0) {
        $names = ($sensitive | Select-Object -ExpandProperty FullName) -join ", "
        throw "构建输入发现敏感或业务资料，请移出源码目录后重试：$names"
    }
}

function Build-Frontend {
    Write-Step "安装并构建前端静态文件"
    $env:VITE_LIFECYCLE_ENABLED = "1"
    $frontend = Join-Path $script:RepoRoot "frontend"
    Invoke-Tool "mise" @("x", "--", "pnpm", "install", "--frozen-lockfile") $frontend
    Invoke-Tool "mise" @("x", "--", "pnpm", "build") $frontend
}

function Build-Backend {
    Write-Step "安装锁定的 Python 依赖"
    $backend = Join-Path $script:RepoRoot "backend"
    Invoke-Tool "mise" @("x", "--", "uv", "sync", "--locked") $backend
    Write-Step "生成 Windows 冻结程序"
    $spec = Join-Path $PSScriptRoot "opinion-workbench.spec"
    # Run PyInstaller in the backend project environment so the frozen
    # analysis sees the same locked runtime dependencies that the packaged
    # application will execute.  ``uv tool run`` creates an isolated tool
    # environment and would otherwise omit FastAPI, Playwright, and the
    # product's other imports.
    Invoke-Tool "mise" @("x", "--", "uv", "run", "--locked", "--python", "3.11", "--with", "pyinstaller==6.16.0", "pyinstaller", $spec, "--noconfirm", "--clean", "--distpath", (Join-Path $script:BuildRoot "app"), "--workpath", (Join-Path $script:BuildRoot "pyinstaller")) $backend
}

function Build-Portable {
    Write-Step "生成 ZIP 免安装版"
    $app = Join-Path $script:BuildRoot "app\OpinionWorkbench"
    foreach ($relative in @("OpinionWorkbench.exe", "OpinionWorkbenchGalleryWorker.exe", "_internal\resources\static\index.html")) {
        if (-not (Test-Path (Join-Path $app $relative) -PathType Leaf)) {
            throw "免安装版缺少必要文件：$relative"
        }
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "portable-readme.txt") -Destination (Join-Path $app "README.txt") -Force
    $version = if ($env:GITHUB_REF_NAME) { $env:GITHUB_REF_NAME } else { "dev" }
    $source = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (& git -C $script:RepoRoot rev-parse HEAD).Trim() }
    if ($env:GITHUB_ACTIONS -and $version -notmatch '^v\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') {
        throw 'Release builds require a semantic version tag.'
    }
    "version=$version", "source=$source", "architecture=x86_64", "minimum_windows=10" |
        Set-Content -LiteralPath (Join-Path $app "BUILD-METADATA.txt") -Encoding ascii
    $archive = Join-Path $script:RepoRoot "dist\windows\OpinionWorkbench-Windows.zip"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    # Include the entire frozen directory, including hidden files and the worker.
    # Never archive the repository or the user's runtime data.
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $app,
        $archive,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $true
    )
    $versioned = Join-Path $script:RepoRoot "dist\windows\OpinionWorkbench-$version-Windows-x64.zip"
    Copy-Item -LiteralPath $archive -Destination $versioned -Force
    (Get-FileHash -Algorithm SHA256 $versioned).Hash.ToLower() + "  " + (Split-Path $versioned -Leaf) |
        Set-Content -LiteralPath "$versioned.sha256" -Encoding ascii
    Write-Host "免安装版：$archive；版本产物：$versioned" -ForegroundColor Green
}

function Build-Installer {
    Write-Step "生成 Inno Setup 安装程序"
    $iscc = Find-InnoCompiler
    if (-not $iscc) { throw "找不到 Inno Setup 编译器 ISCC.exe。" }
    Invoke-Tool $iscc @((Join-Path $PSScriptRoot "installer.iss"))
    $installer = Join-Path $script:RepoRoot "dist\windows\OpinionWorkbench-Setup.exe"
    if (-not (Test-Path $installer)) {
        throw "Inno Setup 未生成预期产物：$installer"
    }
    Write-Host "安装程序：$installer" -ForegroundColor Green
}

try {
    Start-Transcript -Path $script:LogPath -Force | Out-Null
    Assert-Environment
    Assert-CleanInputs
    Reset-BuildOutputs
    Build-Frontend
    Build-Backend
    Build-Portable
    if ($Installer) { Build-Installer }
    if ($PackageToolkit) {
        Write-Step "打包干净的维护者工具包"
        Invoke-Tool "powershell.exe" @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "package-toolkit.ps1")
        )
    }
    Write-Host "构建完成。日志：$script:LogPath" -ForegroundColor Green
}
catch {
    Write-Error $_.Exception.Message
    Write-Host "构建失败，完整日志：$script:LogPath" -ForegroundColor Red
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}

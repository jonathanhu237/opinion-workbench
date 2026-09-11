[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stage = Join-Path $PSScriptRoot "build\toolkit"
$archive = Join-Path $repo "dist\windows\Longtian-Windows-Build-Toolkit.zip"

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

# Keep the package source explicit.  In particular, never copy the repository
# root recursively: a developer's runtime, .env, browser profile or database
# must not become part of a distributable toolkit.
$files = @(
    "README.md",
    "AGENTS.md",
    "mise.toml",
    "backend\pyproject.toml",
    "backend\uv.lock",
    "backend\.python-version",
    "backend\README.md",
    "frontend\package.json",
    "frontend\pnpm-lock.yaml",
    "frontend\index.html",
    "frontend\vite.config.ts",
    "frontend\tsconfig.json",
    "frontend\tsconfig.app.json",
    "frontend\tsconfig.node.json",
    "frontend\components.json",
    "frontend\prettier.config.mjs",
    "frontend\.node-version",
    "windows\README.md",
    "windows\portable-readme.txt",
    "windows\build.cmd",
    "windows\build.ps1",
    "windows\launcher_entry.py",
    "windows\longtian.spec",
    "windows\installer.iss",
    "windows\package-toolkit.ps1"
)
$directories = @(
    "backend\src",
    "frontend\src"
)

foreach ($relative in $files) {
    $source = Join-Path $repo $relative
    if (-not (Test-Path $source -PathType Leaf)) { throw "工具包输入缺失：$relative" }
    $destination = Join-Path $stage $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}
foreach ($relative in $directories) {
    $source = Join-Path $repo $relative
    if (-not (Test-Path $source -PathType Container)) { throw "工具包目录缺失：$relative" }
    $destination = Join-Path $stage $relative
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Copy-Item -Path (Join-Path $source "*") -Destination $destination -Recurse -Force
}

# Source checkouts often contain bytecode from local tests.  It is useless to
# a Windows build and can leak host-specific paths into the toolkit, so remove
# it after the explicit source copy.
Get-ChildItem -LiteralPath $stage -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "__pycache__" } |
    Sort-Object FullName -Descending |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $stage -Recurse -Force -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
    Remove-Item -Force

$forbidden = Get-ChildItem -LiteralPath $stage -Recurse -Force -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like "*.sqlite3" -or $_.Name -like "*.key" -or $_.Name -like ".env*" -or
        $_.FullName -match "runtime|managed-chrome|node_modules|dist|logs"
    }
if ($forbidden.Count -gt 0) {
    throw "工具包仍包含运行时或敏感资料：$($forbidden.FullName -join ', ')"
}

New-Item -ItemType Directory -Force -Path (Split-Path $archive) | Out-Null
if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }
# PowerShell's wildcard form silently omits dotfiles (including
# frontend\.node-version).  The .NET API enumerates hidden entries as well and
# stores the staging directory's contents at the archive root.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $stage,
    $archive,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)
Write-Host "维护者工具包：$archive" -ForegroundColor Green

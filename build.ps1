<#
.SYNOPSIS
影之诗自动对战脚本 - 打包脚本

.DESCRIPTION
使用 PyInstaller 打包项目，并自动复制所需资源目录
#>

param(
    [string]$DistDir = "dist\Svb_Byd_Deck_Auto"
)

# 设置控制台编码
$OutputEncoding = [console]::InputEncoding = [console]::OutputEncoding = New-Object System.Text.UTF8Encoding
Push-Location -LiteralPath $PSScriptRoot

$expectedDistName = "Svb_Byd_Deck_Auto"
$distName = Split-Path -Leaf $DistDir
$distParent = Split-Path -Parent $DistDir
if (-not $distParent) {
    $distParent = "."
}
if ($distName -ne $expectedDistName) {
    Write-Host "错误: DistDir 最后一层必须为 $expectedDistName" -ForegroundColor Red
    Pop-Location
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  影之诗自动对战脚本 - 打包脚本" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 检查项目虚拟环境及打包工具
$pythonPath = ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    Write-Host "错误: 虚拟环境不存在 - $pythonPath" -ForegroundColor Red
    Read-Host "按回车键退出..."
    Pop-Location
    exit 1
}

# 检查 PyInstaller，不依赖当前 PowerShell 是否已激活虚拟环境
Write-Host "[1/3] 检查打包环境..." -ForegroundColor Yellow
try {
    & $pythonPath -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "缺少 PyInstaller，请先运行：.venv\Scripts\python.exe -m pip install -r requirements-build.in"
    }
    Write-Host "打包环境可用" -ForegroundColor Green
}
catch {
    Write-Host "错误: $_" -ForegroundColor Red
    Read-Host "按回车键退出..."
    Pop-Location
    exit 1
}

# 执行打包
Write-Host ""
Write-Host "[2/3] 执行 PyInstaller 打包..." -ForegroundColor Yellow
try {
    & $pythonPath -m PyInstaller --noconfirm --clean --distpath $distParent main.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 执行失败"
    }
    Write-Host "打包完成" -ForegroundColor Green
}
catch {
    Write-Host "错误: $_" -ForegroundColor Red
    Read-Host "按回车键退出..."
    Pop-Location
    exit 1
}

# 复制资源目录到 dist 目录
Write-Host ""
Write-Host "[3/3] 复制资源目录..." -ForegroundColor Yellow

$requiredDirs = @(
    "quanka\SV_WB_Cards",
    "Image",
    "templates",
    "templates_global",
    "card_cost",
    "说明文档（必看）"
)

foreach ($dir in $requiredDirs) {
    $sourcePath = ".\$dir"
    $destPath = "$DistDir\$dir"
    
    if (Test-Path $sourcePath) {
        # 创建目标目录
        if (-not (Test-Path $destPath)) {
            New-Item -ItemType Directory -Path $destPath | Out-Null
        }
        
        # 复制目录内容
        Copy-Item -Path "$sourcePath\*" -Destination $destPath -Recurse -Force
        Write-Host "已复制: $dir" -ForegroundColor Green
    }
    else {
        Write-Host "警告: $dir 目录不存在" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  打包完成!" -ForegroundColor Green
Write-Host "  可执行文件位置: $DistDir\Svb_Byd_Deck_Auto.exe" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Pop-Location
Read-Host "按回车键退出..."

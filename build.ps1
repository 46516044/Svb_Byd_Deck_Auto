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

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  影之诗自动对战脚本 - 打包脚本" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 检查虚拟环境是否存在
$venvPath = ".venv\Scripts\activate"
if (-not (Test-Path $venvPath)) {
    Write-Host "错误: 虚拟环境不存在 - $venvPath" -ForegroundColor Red
    Read-Host "按回车键退出..."
    exit 1
}

# 进入虚拟环境
Write-Host "[1/3] 激活虚拟环境..." -ForegroundColor Yellow
try {
    & $venvPath
    if (-not $?) {
        throw "激活虚拟环境失败"
    }
    Write-Host "虚拟环境已激活" -ForegroundColor Green
}
catch {
    Write-Host "错误: $_" -ForegroundColor Red
    Read-Host "按回车键退出..."
    exit 1
}

# 执行打包
Write-Host ""
Write-Host "[2/3] 执行 PyInstaller 打包..." -ForegroundColor Yellow
try {
    pyinstaller main.spec
    if (-not $?) {
        throw "PyInstaller 执行失败"
    }
    Write-Host "打包完成" -ForegroundColor Green
}
catch {
    Write-Host "错误: $_" -ForegroundColor Red
    Read-Host "按回车键退出..."
    exit 1
}

# 复制资源目录到 dist 目录
Write-Host ""
Write-Host "[3/3] 复制资源目录..." -ForegroundColor Yellow

$requiredDirs = @(
    "quanka",
    "Image",
    "templates",
    "templates_global",
    "card_cost",
    "shadowverse_cards_cost"
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
Read-Host "按回车键退出..."

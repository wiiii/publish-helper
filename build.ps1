# Publish Helper EXE Builder - PowerShell Version
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Publish Helper EXE Builder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 选择解释器：优先项目内 .venv
# 直接往全局 Python 装 requirements.txt 会把别的项目的库降级
# （例如 requests / pyperclip / click 被压回旧版，连带打挂 pywidevine、mitmproxy 等）
$py = "python"
if (Test-Path ".venv\Scripts\python.exe") {
    $py = ".venv\Scripts\python.exe"
    Write-Host "[INFO] Using project venv: .venv\Scripts\python.exe" -ForegroundColor Cyan
} else {
    Write-Host "[WARN] .venv not found, falling back to global python" -ForegroundColor Yellow
    Write-Host "       Run 'python -m venv .venv' first to keep the global env clean." -ForegroundColor Yellow
}
Write-Host ""

# Check Python
Write-Host "[1/6] Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = & $py --version 2>&1
    Write-Host "[OK] Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found! Please install Python 3.9+" -ForegroundColor Red
    pause
    exit 1
}
Write-Host ""

# Clean old builds
Write-Host "[2/6] Cleaning old builds..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
Write-Host "[OK] Cleaned" -ForegroundColor Green
Write-Host ""

# Install PyInstaller
Write-Host "[3/6] Installing PyInstaller..." -ForegroundColor Yellow
& $py -m pip install pyinstaller -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install PyInstaller" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "[OK] PyInstaller installed" -ForegroundColor Green
Write-Host ""

# Install dependencies
Write-Host "[4/6] Installing dependencies..." -ForegroundColor Yellow
& $py -m pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "[OK] Dependencies installed" -ForegroundColor Green
Write-Host ""

# Run PyInstaller
Write-Host "[5/6] Packaging... This may take a few minutes." -ForegroundColor Yellow
& $py -m PyInstaller --clean publish-helper.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Packaging failed!" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "[OK] Packaging complete" -ForegroundColor Green
Write-Host ""

# Verify output
Write-Host "[6/6] Verifying output..." -ForegroundColor Yellow
$exePath = Join-Path "dist" "Publish Helper.exe"

if (Test-Path $exePath) {
    Write-Host "[OK] Single EXE created - all dependencies included" -ForegroundColor Green
    Write-Host "     The EXE contains all Python runtime and libraries" -ForegroundColor Green
} else {
    Write-Host "[ERROR] EXE not found!" -ForegroundColor Red
    pause
    exit 1
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SUCCESS! Build complete." -ForegroundColor Green
Write-Host "Output: dist\Publish Helper.exe" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
pause

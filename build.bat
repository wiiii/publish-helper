@echo off
setlocal enabledelayedexpansion

:: Set UTF-8 encoding
chcp 65001 >nul 2>&1

echo ========================================
echo Publish Helper EXE Builder
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.9+
    pause
    exit /b 1
)
echo [OK] Python found
echo.

:: Clean old builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [OK] Cleaned old builds
echo.

:: Install PyInstaller
echo Installing PyInstaller...
pip install pyinstaller -q
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller
    pause
    exit /b 1
)
echo [OK] PyInstaller installed
echo.

:: Install dependencies
echo Installing dependencies...
pip install -r requirements.txt -q
echo [OK] Dependencies installed
echo.

:: Run PyInstaller
echo Packaging... This may take a few minutes.
pyinstaller --clean publish-helper.spec
if errorlevel 1 (
    echo [ERROR] Packaging failed!
    pause
    exit /b 1
)
echo [OK] Packaging complete
echo.

:: Verify output
echo Verifying output...
if exist "dist\Publish Helper.exe" (
    echo [OK] Single EXE created - all dependencies included
    echo      The EXE contains all Python runtime and libraries
) else (
    echo [ERROR] EXE not found!
    pause
    exit /b 1
)
echo.

echo ========================================
echo SUCCESS! Build complete.
echo Output: dist\Publish Helper.exe
echo ========================================
echo.
pause

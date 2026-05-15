@echo off
REM ============================================================
REM  DCM Tool - Windows Build Script
REM  Requirements: Python 3.9+, pip
REM  Run this from the project root directory.
REM ============================================================

echo [1/4] Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.9+.
    pause
    exit /b 1
)

echo [2/4] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/4] Building executable with PyInstaller...
pyinstaller DCM_Tool.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo [4/4] Build complete!
echo Output directory: dist\DCM_Tool\
echo Executable: dist\DCM_Tool\DCM_Tool.exe
echo.
echo You can now copy the dist\DCM_Tool\ folder to any Windows machine.
pause

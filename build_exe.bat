@echo off
REM SentinelLite Windows packaging script (PROJECT_SPEC.md section 21).
REM
REM Builds a standalone Windows executable with PyInstaller:
REM     dist\SentinelLite\SentinelLite.exe
REM
REM Run this from a Windows checkout of the repository, inside the
REM project's virtual environment (see README.md "Development Setup").
REM
REM Usage:
REM     build_exe.bat
REM
setlocal

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [SentinelLite] pyinstaller was not found on PATH.
    echo [SentinelLite] Install dependencies first: pip install -r requirements.txt
    exit /b 1
)

echo [SentinelLite] Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [SentinelLite] Building SentinelLite.exe with PyInstaller...
pyinstaller --noconfirm --windowed --name SentinelLite ^
    --add-data "assets;assets" ^
    app.py

if errorlevel 1 (
    echo [SentinelLite] Build failed. See the PyInstaller output above.
    exit /b 1
)

echo.
echo [SentinelLite] Build complete: dist\SentinelLite\SentinelLite.exe
echo [SentinelLite] Application data is written to %%LOCALAPPDATA%%\SentinelLite\
echo [SentinelLite] (database, logs, exports) -- not to the install directory.

endlocal

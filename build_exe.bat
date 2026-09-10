@echo off
REM SentinelLite packaging script (PROJECT_SPEC.md sections 21 and 32).
REM
REM Builds a standalone Windows executable with PyInstaller. Run this from
REM a Windows machine with Python 3.12+ and the project's dependencies
REM installed (see README.md "Development Setup").
REM
REM Usage:
REM     build_exe.bat
REM
REM Output:
REM     dist\SentinelLite\SentinelLite.exe

setlocal

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [SentinelLite] PyInstaller was not found on PATH.
    echo [SentinelLite] Install dependencies first:  pip install -r requirements.txt
    exit /b 1
)

echo [SentinelLite] Building SentinelLite.exe with PyInstaller...

pyinstaller --noconfirm --windowed --name SentinelLite app.py

if errorlevel 1 (
    echo [SentinelLite] Build failed. See the PyInstaller output above.
    exit /b 1
)

echo.
echo [SentinelLite] Build complete.
echo [SentinelLite] Output: dist\SentinelLite\SentinelLite.exe
echo.
echo [SentinelLite] A single-file build can be attempted instead with:
echo     pyinstaller --noconfirm --windowed --onefile --name SentinelLite app.py
echo [SentinelLite] but the onedir build above is preferred for reliability
echo [SentinelLite] (PROJECT_SPEC.md section 21).

endlocal

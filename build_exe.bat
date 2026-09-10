@echo off
REM SentinelLite packaging script (PROJECT_SPEC.md section 21).
REM
REM Builds a standalone Windows executable with PyInstaller:
REM   dist\SentinelLite\SentinelLite.exe
REM
REM Usage (from a Windows shell, inside the project's virtual environment):
REM   build_exe.bat

setlocal

echo === SentinelLite build ===

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pyinstaller was not found on PATH.
    echo         Install project dependencies first:
    echo             pip install -r requirements.txt
    exit /b 1
)

echo Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Running PyInstaller...
pyinstaller --noconfirm --windowed --name SentinelLite app.py
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed. See output above.
    exit /b 1
)

if not exist "dist\SentinelLite\SentinelLite.exe" (
    echo [ERROR] Build finished but dist\SentinelLite\SentinelLite.exe was not produced.
    exit /b 1
)

echo.
echo === Build succeeded ===
echo   dist\SentinelLite\SentinelLite.exe
echo.
echo Run the Final Acceptance Test (PROJECT_SPEC.md section 33) against this
echo build before shipping it.

endlocal

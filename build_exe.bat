@echo off
REM SentinelLite packaging script (PROJECT_SPEC.md section 21, Run 7).
REM
REM Builds a standalone Windows executable with PyInstaller:
REM
REM     dist\SentinelLite\SentinelLite.exe
REM
REM Usage (from the project root, with the project's virtual environment
REM activated so the exact pinned dependencies in requirements.txt are
REM used):
REM
REM     build_exe.bat
REM
REM Reliability is preferred over a single-file build (section 21), so
REM this uses the default one-folder output. A --onefile build can be
REM produced instead by adding --onefile to the pyinstaller command below,
REM at the cost of a slower startup (self-extracting) and, historically,
REM higher false-positive rates from antivirus/SmartScreen on unsigned
REM single-file executables.

setlocal

echo Installing/verifying dependencies...
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Building SentinelLite.exe with PyInstaller...
pyinstaller --noconfirm --windowed --name SentinelLite app.py
if errorlevel 1 goto :error

echo.
echo Build succeeded: dist\SentinelLite\SentinelLite.exe
echo Launch it to verify the packaged application before distributing it.
goto :eof

:error
echo.
echo Build failed. See the output above for details.
exit /b 1

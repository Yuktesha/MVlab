@echo off
cd /d "%~dp0"
echo Starting ChronoStretch...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not installed or not in your PATH.
    echo Please install Python from https://www.python.org/
    pause
    exit
)

python chrono_stretch.py %*
if %errorlevel% neq 0 pause

@echo off
cd /d "%~dp0"
echo Starting ChronoStretch Pro with your files...
python ChronoStretch.py %*
if %errorlevel% neq 0 pause

@echo off
setlocal

rem Starts BTBatteryLab: the Python collector and BluetoothWatcher
rem (C#), each in its own console window.
rem
rem Order matters: the Python collector starts first because
rem JsonlTailMonitor only follows *new* lines written to the JSONL
rem from that moment on (see README.md, Getting Started section) - if
rem BluetoothWatcher wrote its initial events before Python was
rem listening, those events would be lost.

set "ROOT=%~dp0"

echo BTBatteryLab - starting up
echo --------------------------
echo.

if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo [ERROR] Can't find %ROOT%.venv\Scripts\python.exe
    echo.
    echo Create the virtual environment and install the package first:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -e .
    echo.
    pause
    exit /b 1
)

where dotnet >nul 2>nul
if errorlevel 1 (
    echo [ERROR] "dotnet" not found in PATH.
    echo Install the .NET 8 SDK: https://dotnet.microsoft.com/download
    echo.
    pause
    exit /b 1
)

echo Starting the Python collector...
start "BTBatteryLab - Python Collector" cmd /k ""%ROOT%.venv\Scripts\python.exe" -m btbatterylab.main"

echo Waiting for the collector to be ready before starting BluetoothWatcher...
timeout /t 3 /nobreak >nul

echo Starting BluetoothWatcher...
start "BTBatteryLab - BluetoothWatcher" cmd /k "cd /d "%ROOT%BluetoothWatcher" && dotnet run"

echo.
echo Both started in separate windows.
echo To stop them: press ENTER in the BluetoothWatcher window, then
echo CTRL+C in the Python collector one.
echo This window can be closed.
echo.
pause

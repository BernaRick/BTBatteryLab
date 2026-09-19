@echo off
setlocal

rem Starts BTBatteryLab: the Python collector and BluetoothWatcher
rem (C#), both running invisibly in the background - no console
rem windows, unlike before (see the "why" below). Once started:
rem   - The Python collector opens its dashboard in your browser
rem     automatically (Start/Stop for monitoring, the historical
rem     view, and an Exit button to close it).
rem   - BluetoothWatcher has no UI of its own - stop it with stop.bat.
rem
rem Why no windows: with the collector's own dashboard now showing
rem its status, status, and battery history in the browser, two
rem console windows just sitting open duplicated that for no reason.
rem The trade-off: neither process has a console to Ctrl+C/press
rem ENTER in any more - see stop.bat, and the dashboard's own Exit
rem button, for how to stop them instead.
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

if not exist "%ROOT%.venv\Scripts\pythonw.exe" (
    echo [ERROR] Can't find %ROOT%.venv\Scripts\pythonw.exe
    echo.
    echo Create the virtual environment and install the package first:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -e .
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

echo Starting the Python collector (its dashboard opens in your browser)...
rem pythonw.exe is the windowless variant of python.exe that ships
rem with every install - unlike python.exe, it never allocates a
rem console window, so no cmd wrapper is needed here any more.
start "" "%ROOT%.venv\Scripts\pythonw.exe" -m btbatterylab.main

echo Waiting for the collector to be ready before starting BluetoothWatcher...
timeout /t 3 /nobreak >nul

echo Building BluetoothWatcher...
rem A plain "dotnet run" would still show a console window here - that
rem window belongs to dotnet.exe itself (the CLI host), not to
rem BluetoothWatcher, so BluetoothWatcher.csproj's own OutputType=
rem WinExe can't hide it. Building first and launching the resulting
rem .exe directly avoids that entirely: this build step runs in THIS
rem window (already open since you started run.bat), and the actual
rem BluetoothWatcher.exe never allocates a console of its own.
dotnet build "%ROOT%BluetoothWatcher" -c Debug --nologo -v quiet
if errorlevel 1 (
    echo [ERROR] BluetoothWatcher failed to build - see the output above.
    pause
    exit /b 1
)

echo Starting BluetoothWatcher...
start "" "%ROOT%BluetoothWatcher\bin\Debug\net8.0-windows10.0.19041.0\BluetoothWatcher.exe"

echo.
echo Both are now running in the background - no windows to keep open.
echo Your browser should have opened BTBatteryLab's dashboard already;
echo if not, something failed to start - check
echo Documents\BTBatteryLabData\logs\btbatterylab.log.
echo.
echo To stop everything: click the exit icon in the dashboard (stops
echo the Python side), then run stop.bat (stops BluetoothWatcher).
echo This window can be closed.
echo.
pause

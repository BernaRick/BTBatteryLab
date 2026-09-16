@echo off
setlocal

rem Avvia BTBatteryLab: il collector Python e BluetoothWatcher (C#),
rem ciascuno nella propria finestra di console.
rem
rem Ordine importante: il collector Python parte per primo perche'
rem JsonlTailMonitor segue solo le righe *nuove* scritte nel JSONL da
rem quel momento in poi (vedi README.md, sezione Getting Started) - se
rem BluetoothWatcher scrivesse i suoi eventi iniziali prima che Python
rem sia in ascolto, quegli eventi andrebbero persi.

set "ROOT=%~dp0"

echo BTBatteryLab - avvio
echo --------------------
echo.

if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo [ERRORE] Non trovo %ROOT%.venv\Scripts\python.exe
    echo.
    echo Crea prima il virtual environment e installa il pacchetto:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -e .
    echo.
    pause
    exit /b 1
)

where dotnet >nul 2>nul
if errorlevel 1 (
    echo [ERRORE] "dotnet" non trovato nel PATH.
    echo Installa il .NET 8 SDK: https://dotnet.microsoft.com/download
    echo.
    pause
    exit /b 1
)

echo Avvio il collector Python...
start "BTBatteryLab - Collector Python" cmd /k ""%ROOT%.venv\Scripts\python.exe" -m btbatterylab.main"

echo In attesa che il collector sia pronto prima di avviare BluetoothWatcher...
timeout /t 3 /nobreak >nul

echo Avvio BluetoothWatcher...
start "BTBatteryLab - BluetoothWatcher" cmd /k "cd /d "%ROOT%BluetoothWatcher" && dotnet run"

echo.
echo Avviati entrambi in finestre separate.
echo Per fermarli: premi ENTER nella finestra di BluetoothWatcher, poi
echo CTRL+C in quella del collector Python.
echo Questa finestra puo' essere chiusa.
echo.
pause

@echo off
setlocal

rem Pacchettizza BTBatteryLab in una cartella pronta per la
rem distribuzione: un solo eseguibile da avviare
rem (dist\release\BluetoothWatcher.exe), che si porta dietro il
rem collector Python gia' pronto all'uso - chi lo USA non deve avere
rem Python, .NET o git installati. Servono solo qui, per COSTRUIRLO.
rem
rem Prerequisiti per la build (vedi anche README.md):
rem   - .venv gia' creato con: python -m venv .venv ^&^& .venv\Scripts\pip install -e .
rem   - .NET 8 SDK
rem   - PyInstaller: lo installa questo script stesso se manca

set "ROOT=%~dp0"
set "DIST=%ROOT%dist\release"

echo BTBatteryLab - build standalone
echo --------------------------------
echo.

rem Se una build precedente e' ancora in esecuzione (BluetoothWatcher.exe
rem e/o il collector btbatterylab.exe che lancia in background), i loro
rem file restano aperti e PyInstaller/dotnet non riescono a sovrascriverli
rem (Windows nega la cancellazione di un file aperto da un altro processo -
rem vedi anche il fix analogo in BluetoothWatcher/Program.cs). Li chiudiamo
rem noi prima di ripartire, cosi' non serve farlo a mano ad ogni rebuild.
taskkill /F /IM btbatterylab.exe /T >nul 2>nul
taskkill /F /IM BluetoothWatcher.exe /T >nul 2>nul

if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo [ERRORE] Non trovo %ROOT%.venv\Scripts\python.exe
    echo.
    echo Crea prima il virtual environment:
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

rem Usiamo sempre "python -m ..." invece degli .exe separati in
rem Scripts\ (pip.exe, pyinstaller.exe): quegli shim a volte mancano o
rem vengono messi in quarantena dall'antivirus, mentre il modulo
rem funziona sempre finche' funziona python.exe.
"%ROOT%.venv\Scripts\python.exe" -c "import pip" 2>nul
if errorlevel 1 (
    echo pip non e' presente in questo virtual environment, lo installo con ensurepip...
    "%ROOT%.venv\Scripts\python.exe" -m ensurepip --upgrade
    if errorlevel 1 (
        echo [ERRORE] Impossibile installare pip nel virtual environment.
        echo Prova a ricrearlo da zero:
        echo     rmdir /s /q .venv
        echo     python -m venv .venv
        echo     .venv\Scripts\python.exe -m pip install -e .
        pause
        exit /b 1
    )
    echo.
)

"%ROOT%.venv\Scripts\python.exe" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller non e' installato nel virtual environment, lo installo...
    "%ROOT%.venv\Scripts\python.exe" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERRORE] Installazione di PyInstaller fallita.
        pause
        exit /b 1
    )
    echo.
)

if exist "%DIST%" (
    echo Pulisco la build precedente in %DIST%...
    rmdir /s /q "%DIST%"
    echo.
)

echo [1/3] Pacchettizzo il collector Python con PyInstaller...
pushd "%ROOT%"
"%ROOT%.venv\Scripts\python.exe" -m PyInstaller btbatterylab.spec --noconfirm
if errorlevel 1 (
    echo [ERRORE] Build PyInstaller fallita.
    popd
    pause
    exit /b 1
)
popd
echo.

echo [2/3] Pubblico BluetoothWatcher (self-contained, win-x64)...
dotnet publish "%ROOT%BluetoothWatcher" -c Release -r win-x64 --self-contained true -o "%DIST%"
if errorlevel 1 (
    echo [ERRORE] dotnet publish fallito.
    pause
    exit /b 1
)
echo.

echo [3/3] Copio il collector Python pacchettizzato nella build...
xcopy /e /i /y "%ROOT%dist\btbatterylab" "%DIST%\btbatterylab\" >nul
echo.

echo Fatto. Eseguibile pronto in:
echo     %DIST%\BluetoothWatcher.exe
echo.
echo Basta un doppio click su BluetoothWatcher.exe: avvia anche il
echo collector Python in background (log in
echo Documents\BTBatteryLabData\collector.log), senza aprire una
echo seconda finestra di console.
echo.
echo Nota: questa build si porta dietro il path dati che main.py ha
echo oggi hardcoded (la cartella Documents di Patrick) - non e' ancora
echo portabile su un altro PC finche' non esiste un configuration
echo system (vedi docs/roadmap.md).
echo.
pause

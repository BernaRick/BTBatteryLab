@echo off
setlocal

rem Packages BTBatteryLab into a folder ready for distribution: a
rem single executable to launch (dist\release\BluetoothWatcher.exe)
rem that brings along the Python collector, already to use - whoever
rem USES it doesn't need Python, .NET or git installed. Those are only
rem needed here, to BUILD it.
rem
rem Build prerequisites (see also README.md):
rem   - .venv already created with: python -m venv .venv ^&^& .venv\Scripts\pip install -e .
rem   - .NET 8 SDK
rem   - PyInstaller: this script installs it itself if missing

set "ROOT=%~dp0"
set "DIST=%ROOT%dist\release"

rem PyInstaller writes its "raw" output (dist\btbatterylab, before the
rem final copy in step 3) under %TEMP%, not inside the repo: the repo
rem lives under OneDrive, which syncs every file as soon as it's
rem created or modified. PyInstaller generates dozens of small files
rem (the DLLs in _internal), and on the next rebuild, when it tries to
rem delete that folder to recreate it from scratch, OneDrive may still
rem be holding a file's handle to hash/upload it, and the deletion
rem fails with "Access is denied" - even with no process of ours
rem running (which is why taskkill alone wasn't enough). %TEMP% isn't
rem synced by OneDrive, so deletion there is always immediate.
set "PYIBUILD=%TEMP%\btbatterylab_pyibuild"

echo BTBatteryLab - standalone build
echo --------------------------------
echo.

rem If a previous build is still running (BluetoothWatcher.exe and/or
rem the btbatterylab.exe collector it launches in the background),
rem their files stay open and PyInstaller/dotnet can't overwrite them
rem (Windows refuses to delete a file another process has open - see
rem also the equivalent fix in BluetoothWatcher/Program.cs). We close
rem both of them ourselves before starting, so it doesn't have to be
rem done by hand before every rebuild.
taskkill /F /IM btbatterylab.exe /T >nul 2>nul
taskkill /F /IM BluetoothWatcher.exe /T >nul 2>nul

if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo [ERROR] Can't find %ROOT%.venv\Scripts\python.exe
    echo.
    echo Create the virtual environment first:
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

rem We always use "python -m ..." instead of the separate .exe shims
rem in Scripts\ (pip.exe, pyinstaller.exe): those shims sometimes go
rem missing or get quarantined by antivirus software, while the module
rem always works as long as python.exe works.
"%ROOT%.venv\Scripts\python.exe" -c "import pip" 2>nul
if errorlevel 1 (
    echo pip isn't present in this virtual environment, installing it with ensurepip...
    "%ROOT%.venv\Scripts\python.exe" -m ensurepip --upgrade
    if errorlevel 1 (
        echo [ERROR] Could not install pip in the virtual environment.
        echo Try recreating it from scratch:
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
    echo PyInstaller isn't installed in the virtual environment, installing it...
    "%ROOT%.venv\Scripts\python.exe" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller installation failed.
        pause
        exit /b 1
    )
    echo.
)

if exist "%DIST%" (
    echo Cleaning up the previous build in %DIST%...
    rmdir /s /q "%DIST%"
    echo.
)

echo [1/3] Packaging the Python collector with PyInstaller...
if exist "%PYIBUILD%" (
    rmdir /s /q "%PYIBUILD%"
)
pushd "%ROOT%"
"%ROOT%.venv\Scripts\python.exe" -m PyInstaller btbatterylab.spec --noconfirm ^
    --distpath "%PYIBUILD%\dist" --workpath "%PYIBUILD%\build"
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    popd
    pause
    exit /b 1
)
popd
echo.

echo [2/3] Publishing BluetoothWatcher (self-contained, win-x64)...
dotnet publish "%ROOT%BluetoothWatcher" -c Release -r win-x64 --self-contained true -o "%DIST%"
if errorlevel 1 (
    echo [ERROR] dotnet publish failed.
    pause
    exit /b 1
)
echo.

echo [3/3] Copying the packaged Python collector into the build...
xcopy /e /i /y "%PYIBUILD%\dist\btbatterylab" "%DIST%\btbatterylab\" >nul
echo.

echo Done. Executable ready at:
echo     %DIST%\BluetoothWatcher.exe
echo.
echo Just double-click BluetoothWatcher.exe: it also starts the
echo Python collector in the background, without opening a second
echo console window. Its log output goes to two places:
echo     Documents\BTBatteryLabData\collector.log          (raw console output)
echo     Documents\BTBatteryLabData\logs\btbatterylab.log  (structured, leveled, rotating)
echo.
echo The data folder (Documents\BTBatteryLabData) and its config.json
echo are resolved automatically for whichever Windows account runs
echo this .exe - see the README's Configuration section to change any
echo of the default settings.
echo.
pause

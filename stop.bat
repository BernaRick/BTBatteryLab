@echo off
setlocal

rem Stops BluetoothWatcher, started by run.bat. Both processes run.bat
rem starts now run without a visible window (see run.bat's own
rem comments), so there's no console to Ctrl+C or press ENTER in any
rem more:
rem   - The Python collector: stop it from its own dashboard tab, in
rem     the browser - click the exit icon there. That closes the
rem     whole Python process, not just the collector inside it.
rem   - BluetoothWatcher: this script.

echo Stopping BluetoothWatcher...
taskkill /F /IM BluetoothWatcher.exe /T >nul 2>nul
if errorlevel 1 (
    echo BluetoothWatcher wasn't running.
) else (
    echo Done.
)

echo.
echo Reminder: this only stops BluetoothWatcher. Stop the Python
echo collector from its own dashboard tab (the exit icon in the
echo header).
echo.
pause

@echo off
setlocal

rem Runs BTBatteryLab's automated test suite with a friendlier console
rem runner (tests\run_tests.py) than the raw
rem `python -m unittest discover -s tests`: buffered output (so a test
rem that deliberately triggers an error/warning path doesn't look like
rem a crash) plus a colored pass/fail summary. See the "Automated
rem tests" section of README.md.
rem
rem Meant to be run by anyone - including a non-technical user asked
rem to run this to help diagnose a problem, not just contributors - so
rem this double-clicks and stays open to show the result.

set "ROOT=%~dp0"

echo BTBatteryLab - running the automated test suite
echo -------------------------------------------------
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

"%ROOT%.venv\Scripts\python.exe" "%ROOT%tests\run_tests.py"
set "TEST_EXIT_CODE=%ERRORLEVEL%"

echo.
pause
exit /b %TEST_EXIT_CODE%

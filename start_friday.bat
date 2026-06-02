@echo off
title Friday Assistant
chcp 65001 >nul

set PROJECT=C:\Users\malya\.vscode\python practise\Friday\wake-up
set VENV_PY=%PROJECT%\.venv\Scripts\python.exe
set MAIN=%PROJECT%\main.py
set LOG=%PROJECT%\friday_startup.log
set ERR=%PROJECT%\friday_error.log
set MODEL=%PROJECT%\model

cd /d "%PROJECT%"

echo [%DATE% %TIME%] ===== Friday starting ===== >> "%LOG%"

if not exist "%MODEL%\" (
    echo [%DATE% %TIME%] ERROR: model folder missing >> "%LOG%"
    echo.
    echo  ERROR: Vosk model folder not found!
    echo  Expected: %MODEL%
    echo  Download vosk-model-small-en-us-0.15 from:
    echo  https://alphacephei.com/vosk/models
    echo  Extract and rename the folder to "model"
    echo.
    pause
    exit /b 1
)

if exist "%VENV_PY%" (
    set PYTHON=%VENV_PY%
) else (
    set PYTHON=python
)

echo [%DATE% %TIME%] Python: %PYTHON% >> "%LOG%"

:: Run Friday and capture stderr to error log
"%PYTHON%" "%MAIN%" 2>> "%ERR%"

set EXIT_CODE=%ERRORLEVEL%
echo [%DATE% %TIME%] Friday exited (code %EXIT_CODE%) >> "%LOG%"

echo.
echo ==============================
if %EXIT_CODE% EQU 0 (
    echo  Friday closed normally.
) else (
    echo  Friday exited with error code %EXIT_CODE%
    echo  Check friday_error.log for the full traceback:
    echo  %ERR%
    echo.
    echo  Last few lines of error log:
    echo  ------------------------------
    powershell -Command "if (Test-Path '%ERR%') { Get-Content '%ERR%' -Tail 20 }"
)
echo ==============================
echo.
pause

@echo off
title Friday Assistant
chcp 65001 >nul

set PROJECT=C:\Users\malya\.vscode\python practise\Friday\wake-up
set VENV_PY=%PROJECT%\.venv\Scripts\python.exe
set MAIN=%PROJECT%\main.py
set LOG=%PROJECT%\friday_startup.log
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
    echo  Extract it and rename the folder to "model"
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

"%PYTHON%" "%MAIN%"
set EXIT_CODE=%ERRORLEVEL%
echo [%DATE% %TIME%] Friday exited (code %EXIT_CODE%) >> "%LOG%"

if %EXIT_CODE% NEQ 0 (
    echo.
    echo  *** Friday exited with code %EXIT_CODE% ***
    echo  Check friday_startup.log for details
    echo.
    pause
)

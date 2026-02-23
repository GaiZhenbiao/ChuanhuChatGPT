@echo off
echo Opening ChuanhuChatGPT...

if not exist "%~dp0\ChuanhuChat\Scripts" (
    echo Creating venv...
    python -m venv ChuanhuChat

    cd /d "%~dp0\ChuanhuChat\Scripts"
    call activate.bat

    cd /d "%~dp0"
    python -m pip install --upgrade pip
    pip install -r requirements.txt
)

goto :activate_venv

:launch
%PYTHON% ChuanhuChatbot.py %*
pause

:activate_venv
set PYTHON="%~dp0\ChuanhuChat\Scripts\Python.exe"
echo venv %PYTHON%
goto :launch

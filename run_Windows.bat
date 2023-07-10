@echo off
echo Opening ChuanhuChatGPT...

goto :activate_venv

:launch
%PYTHON% ChuanhuChatbot.py %*
pause

:activate_venv
set PYTHON="%~dp0\venv\Scripts\Python.exe"
echo venv %PYTHON%
goto :launch
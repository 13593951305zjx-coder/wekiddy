@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto :python
py -3 "%~dp0install_ollama.py"
goto :finished
:python
python "%~dp0install_ollama.py"
:finished
if not errorlevel 1 exit /b 0
pause
exit /b 1

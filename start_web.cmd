@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto :failed
set "PYTHONUTF8=1"
if exist "%~dp0audio_llm_backend\.venv\Scripts\python.exe" goto :use_environment
where py >nul 2>&1
if not errorlevel 1 goto :use_launcher
where python >nul 2>&1
if not errorlevel 1 goto :use_python
echo Python was not found. Install Python 3.11 or 3.12 and retry.
goto :failed

:use_environment
"%~dp0audio_llm_backend\.venv\Scripts\python.exe" "%~dp0bootstrap.py" %*
goto :finished

:use_launcher
py -3 "%~dp0bootstrap.py" %*
goto :finished

:use_python
python "%~dp0bootstrap.py" %*
goto :finished

:finished
set "START_EXIT=%ERRORLEVEL%"
if "%START_EXIT%"=="0" exit /b 0
echo Startup failed with exit code %START_EXIT%. Read the error above.
pause
exit /b %START_EXIT%

:failed
pause
exit /b 1

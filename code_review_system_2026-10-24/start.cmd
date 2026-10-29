@echo off
setlocal EnableExtensions

cd /d "%~dp0"
set "PROJECT_ROOT=%~dp0"
set "PYTHON_EXE=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "REQUIREMENTS=%PROJECT_ROOT%requirements.txt"

echo [1/3] Checking the Code Review System environment...

if not exist "%PYTHON_EXE%" (
    echo Project virtual environment not found. Creating .venv...
    py -3.12 -m venv "%PROJECT_ROOT%.venv"
    if errorlevel 1 (
        echo The Python launcher did not create the environment. Trying the default Python...
        python -m venv "%PROJECT_ROOT%.venv"
    )
)

if not exist "%PYTHON_EXE%" goto :environment_error

"%PYTHON_EXE%" -c "import fastapi, uvicorn, openai_codex" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Installing missing dependencies from requirements.txt...
    "%PYTHON_EXE%" -m pip install -r "%REQUIREMENTS%"
    if errorlevel 1 goto :install_error
) else (
    echo [2/3] Dependencies are already installed.
)

echo [3/3] Starting the Code Review System website...
echo.

"%PYTHON_EXE%" "%PROJECT_ROOT%launch.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo The server exited with code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%

:environment_error
echo.
echo Unable to create the project Python environment.
echo Install Python 3.12 from https://www.python.org/downloads/ and try again.
pause
exit /b 1

:install_error
echo.
echo Dependency installation failed. Check the error above and try again.
pause
exit /b 1

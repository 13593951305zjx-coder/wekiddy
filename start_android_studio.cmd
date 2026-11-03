@echo off
setlocal
cd /d "%~dp0"
set "PROJECT_DIR=%~dp0android_audio_llm"
set "STUDIO_EXE=%ANDROID_STUDIO_EXE%"

if not defined STUDIO_EXE set "STUDIO_EXE=%ProgramFiles%\Android\Android Studio\bin\studio64.exe"
if not exist "%STUDIO_EXE%" set "STUDIO_EXE=%ProgramFiles(x86)%\Android\Android Studio\bin\studio64.exe"
if not exist "%STUDIO_EXE%" set "STUDIO_EXE=%LOCALAPPDATA%\Programs\Android Studio\bin\studio64.exe"
if not exist "%STUDIO_EXE%" set "STUDIO_EXE=%LOCALAPPDATA%\Android\Sdk\..\Android Studio\bin\studio64.exe"

if not exist "%STUDIO_EXE%" (
    echo 未找到 Android Studio，将打开工程文件夹。
    explorer "%PROJECT_DIR%"
    pause
    exit /b 0
)

start "AudioInsight Android" "%STUDIO_EXE%" "%PROJECT_DIR%"
exit /b 0

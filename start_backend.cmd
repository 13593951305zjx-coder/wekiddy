@echo off
setlocal EnableExtensions
call "%~dp0start_web.cmd" --mode local --no-browser %*
exit /b %ERRORLEVEL%

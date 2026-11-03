@echo off
setlocal EnableExtensions
call "%~dp0start_web.cmd" --mode mock %*
exit /b %ERRORLEVEL%

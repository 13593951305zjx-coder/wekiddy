@echo off
setlocal EnableExtensions
call "%~dp0start_web.cmd" --mode cloud %*
exit /b %ERRORLEVEL%

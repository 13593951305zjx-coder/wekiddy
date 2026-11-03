@echo off
setlocal EnableExtensions
rem Phone and computer on the same Wi-Fi: open the firewall once, then start the service for the LAN.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\open_lan_firewall.ps1"
call "%~dp0start_web.cmd" --mode local --lan %*
exit /b %ERRORLEVEL%

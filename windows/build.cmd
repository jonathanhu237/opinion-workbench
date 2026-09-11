@echo off
setlocal
set "install_arg=-InstallTools"
for %%A in (%*) do if /I "%%~A"=="-InstallTools" set "install_arg="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %install_arg% %*
set "exit_code=%ERRORLEVEL%"
if not "%exit_code%"=="0" pause
exit /b %exit_code%

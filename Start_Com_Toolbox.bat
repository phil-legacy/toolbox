@echo off
rem Com Toolbox - starts the simulator and opens the page
cd /d "%~dp0"
where python >nul 2>nul && (python com_toolbox.py %*) || (py com_toolbox.py %*)
if errorlevel 1 pause

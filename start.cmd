@echo off
setlocal
title CET Study

pushd "%~dp0"
if errorlevel 1 (
    echo Cannot open the project folder. Extract the ZIP before starting.
    pause
    exit /b 1
)

if not exist "%~dp0start.ps1" (
    echo Cannot find start.ps1. Extract all project files into the same folder.
    popd
    pause
    exit /b 1
)

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "CET_STUDY_EXIT_CODE=%ERRORLEVEL%"
if not "%CET_STUDY_EXIT_CODE%"=="0" (
    echo.
    echo Startup did not finish. Please read the messages above.
    echo See the Windows setup guide in the docs folder for help.
    pause
)
popd
exit /b %CET_STUDY_EXIT_CODE%

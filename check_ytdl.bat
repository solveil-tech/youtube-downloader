@echo off
setlocal
cd /d "%~dp0"
title Youtube Downloader - Source Check

set "CHECK_PYTHON=%~dp0.checkenv\Scripts\python.exe"
set "BOOTSTRAP_PYTHON="

if not exist "%CHECK_PYTHON%" (
    where py >nul 2>nul && set "BOOTSTRAP_PYTHON=py -3"
    if not defined BOOTSTRAP_PYTHON where python >nul 2>nul && set "BOOTSTRAP_PYTHON=python"
    if not defined BOOTSTRAP_PYTHON (
        echo [ERROR] Python was not found. Install Python first.
        pause
        exit /b 1
    )

    echo [1/3] Creating an isolated check environment...
    %BOOTSTRAP_PYTHON% -m venv ".checkenv"
    if errorlevel 1 goto :setup_failed
)

"%CHECK_PYTHON%" -c "import PyQt6, qtawesome, requests" >nul 2>nul
if errorlevel 1 (
    echo [1/3] Installing the required packages for the first check...
    "%CHECK_PYTHON%" -m pip install --disable-pip-version-check -r "requirements.txt"
    if errorlevel 1 goto :setup_failed
)

echo [2/3] Checking ytdl.py syntax and imports...
"%CHECK_PYTHON%" -m py_compile "ytdl.py" "idol_search.py" "media_library.py" "youtube_search.py"
if errorlevel 1 (
    echo.
    echo [FAILED] Syntax check failed.
    pause
    exit /b 1
)
"%CHECK_PYTHON%" -c "import ytdl"
if errorlevel 1 (
    echo.
    echo [FAILED] Import check failed.
    pause
    exit /b 1
)

if not exist "idol_names\idol_aliases.json" (
    echo [FAILED] idol_names\idol_aliases.json is missing.
    pause
    exit /b 1
)
"%CHECK_PYTHON%" -X utf8 "check_idol_search.py"
if errorlevel 1 (
    echo [FAILED] Idol search checks failed.
    pause
    exit /b 1
)
"%CHECK_PYTHON%" -X utf8 "check_media_library.py"
if errorlevel 1 (
    echo [FAILED] Media library checks failed.
    pause
    exit /b 1
)
"%CHECK_PYTHON%" -X utf8 "check_search_ui.py"
if errorlevel 1 (
    echo [FAILED] Search UI check failed.
    pause
    exit /b 1
)

echo [3/3] Starting the source version with idol search...
"%CHECK_PYTHON%" -X utf8 "check_batch_download.py"
if errorlevel 1 (
    echo [FAILED] Batch download check failed.
    pause
    exit /b 1
)
echo Enter a group or member and a YYMMDD date, then click Search.
echo Close the application window to finish this check.
"%CHECK_PYTHON%" "ytdl.py"
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo [FAILED] The application exited with code %APP_EXIT%.
    pause
    exit /b %APP_EXIT%
)

echo.
echo [OK] The application closed normally.
pause
exit /b 0

:setup_failed
echo.
echo [FAILED] Could not prepare the isolated check environment.
echo Check the network connection, then run this file again.
pause
exit /b 1

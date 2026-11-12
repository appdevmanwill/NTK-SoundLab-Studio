@echo off
title NTK SoundLab Studio - Static PWA Launcher
color 0a
echo ======================================================================
echo    NTK SoundLab Studio - Offline PWA (Static Host Mode)
echo ======================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Serving static PWA from working\ on http://127.0.0.1:5000 ...
    cd /d "%~dp0working"
    start /min "" cmd /c "timeout /t 1 /nobreak >nul && start http://127.0.0.1:5000"
    python helper\local_server.py --port 5000
    goto :end
)

where php >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Serving staged frontend assets on http://127.0.0.1:5000 ...
    cd /d "%~dp0desktop\assets"
    start /min "" cmd /c "timeout /t 1 /nobreak >nul && start http://127.0.0.1:5000"
    php -S 127.0.0.1:5000
    goto :end
)

echo [ERROR] Neither Python nor PHP was found in your PATH.
echo Open the portable Windows app in SOFTWARE\PORTABLE\WINDOWS.
pause

:end

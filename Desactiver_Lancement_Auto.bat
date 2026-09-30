@echo off
title Desactiver lancement automatique - Kyaf Edu
color 0C
cls
echo ========================================
echo   DESACTIVER LE LANCEMENT AUTOMATIQUE
echo ========================================
echo.

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\Kyaf Edu Gabon.lnk"

if exist "%LINK%" (
    del "%LINK%"
    echo Lancement automatique DESACTIVE.
) else (
    echo Aucun lancement automatique trouve.
)

echo.
echo Le raccourci sur le Bureau reste disponible.
echo.
pause

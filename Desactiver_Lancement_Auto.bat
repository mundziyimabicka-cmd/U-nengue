@echo off
chcp 65001 >nul
title Desactiver lancement automatique - U nengue
color 0C
cls
echo ========================================
echo   DESACTIVER LE LANCEMENT AUTOMATIQUE
echo ========================================
echo.

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

set "REMOVED=0"
if exist "%STARTUP%\U nengue.lnk" (
    del "%STARTUP%\U nengue.lnk"
    echo - Supprime : U nengue.lnk
    set "REMOVED=1"
)
if exist "%STARTUP%\Kyaf Edu Gabon.lnk" (
    del "%STARTUP%\Kyaf Edu Gabon.lnk"
    echo - Supprime : Kyaf Edu Gabon.lnk
    set "REMOVED=1"
)

if "%REMOVED%"=="0" (
    echo Aucun lancement automatique trouve.
) else (
    echo.
    echo Lancement automatique DESACTIVE.
)

echo.
echo Le raccourci sur le Bureau reste disponible.
echo Pour lancer l'app : double-clic sur Lancer_Kyaf_Edu.bat
echo.
pause

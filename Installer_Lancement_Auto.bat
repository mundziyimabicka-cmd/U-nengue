@echo off
chcp 65001 >nul
title Configuration du lancement automatique - U nengue
color 0B
cls
echo ========================================
echo   CONFIGURATION LANCEMENT AUTOMATIQUE
echo   U nengue - Ecole Primaire Gabon
echo ========================================
echo.

cd /d "%~dp0"
set "APPDIR=%~dp0"
set "APPPATH=%~dp0Lancer_Kyaf_Edu.bat"

echo Dossier de l'application :
echo %APPDIR%
echo.

REM --- Bureau (Desktop ou Bureau en francais) ---
set "DESKTOP=%USERPROFILE%\Desktop"
if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%\Bureau"
if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%\OneDrive\Desktop"
if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%\OneDrive\Bureau"

echo [1/2] Creation du raccourci sur le Bureau...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%DESKTOP%\U nengue.lnk'); $s.TargetPath='%APPPATH%'; $s.WorkingDirectory='%APPDIR%'; $s.WindowStyle=1; $s.Description='U nengue - Gestion ecole primaire Gabon'; $s.Save()"

if exist "%DESKTOP%\U nengue.lnk" (
    echo     OK - Raccourci "U nengue" cree sur le Bureau
) else (
    echo     Essai avec le nom Kyaf Edu Gabon...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%DESKTOP%\Kyaf Edu Gabon.lnk'); $s.TargetPath='%APPPATH%'; $s.WorkingDirectory='%APPDIR%'; $s.Save()"
    if exist "%DESKTOP%\Kyaf Edu Gabon.lnk" (echo     OK - Raccourci cree) else (echo     Attention : raccourci Bureau non cree)
)

echo.
echo [2/2] Ajout au demarrage de Windows...

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%STARTUP%\U nengue.lnk'); $s.TargetPath='%APPPATH%'; $s.WorkingDirectory='%APPDIR%'; $s.WindowStyle=1; $s.Description='U nengue - Demarrage automatique'; $s.Save()"

if exist "%STARTUP%\U nengue.lnk" (
    echo     OK - Lancement automatique active
) else (
    echo     Attention : demarrage auto non configure
    echo     Vous pouvez lancer l'app avec Lancer_Kyaf_Edu.bat
)

echo.
echo ========================================
echo   TERMINE
echo ========================================
echo.
echo Ce qui a ete configure :
echo.
echo  1. Raccourci sur le Bureau : "U nengue"
echo     -^> Double-cliquez dessus pour lancer l'app
echo.
echo  2. Lancement automatique au demarrage de Windows
echo     -^> L'application peut se lancer a l'allumage
echo.
echo Pour LANCER l'application maintenant :
echo  - Double-clic sur Lancer_Kyaf_Edu.bat
echo  - Ou le raccourci Bureau "U nengue"
echo.
echo Puis ouvrez : http://127.0.0.1:5000
echo.
echo Pour DESACTIVER le lancement automatique :
echo  - Double-clic sur Desactiver_Lancement_Auto.bat
echo  - Ou Windows+R puis shell:startup puis supprimez "U nengue"
echo.
echo ========================================
pause

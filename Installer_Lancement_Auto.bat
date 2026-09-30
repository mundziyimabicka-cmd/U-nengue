@echo off
title Configuration du lancement automatique - Kyaf Edu
color 0B
cls
echo ========================================
echo   CONFIGURATION LANCEMENT AUTOMATIQUE
echo   Kyaf Edu Gabon
echo ========================================
echo.

cd /d "%~dp0"
set "APPDIR=%~dp0"
set "APPPATH=%~dp0Lancer_Kyaf_Edu.bat"

echo Dossier de l'application :
echo %APPDIR%
echo.

REM --- 1. Raccourci sur le Bureau ---
echo [1/2] Creation du raccourci sur le Bureau...

set "DESKTOP=%USERPROFILE%\Desktop"
if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%\Bureau"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%DESKTOP%\Kyaf Edu Gabon.lnk'); ^
   $s.TargetPath = '%APPPATH%'; ^
   $s.WorkingDirectory = '%APPDIR%'; ^
   $s.WindowStyle = 1; ^
   $s.Description = 'Kyaf Edu - Gestion ecole primaire Gabon'; ^
   $s.Save()"

if exist "%DESKTOP%\Kyaf Edu Gabon.lnk" (
    echo     OK - Raccourci cree sur le Bureau
) else (
    echo     Attention : raccourci Bureau non cree
)

echo.

REM --- 2. Demarrage automatique avec Windows ---
echo [2/2] Ajout au demarrage de Windows...

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%STARTUP%\Kyaf Edu Gabon.lnk'); ^
   $s.TargetPath = '%APPPATH%'; ^
   $s.WorkingDirectory = '%APPDIR%'; ^
   $s.WindowStyle = 1; ^
   $s.Description = 'Kyaf Edu - Demarrage automatique'; ^
   $s.Save()"

if exist "%STARTUP%\Kyaf Edu Gabon.lnk" (
    echo     OK - Lancement automatique active
) else (
    echo     Attention : demarrage auto non configure
)

echo.
echo ========================================
echo   TERMINE
echo ========================================
echo.
echo Ce qui a ete configure :
echo.
echo  1. Raccourci sur le Bureau : "Kyaf Edu Gabon"
echo     -^> Double-cliquez dessus pour lancer l'app
echo.
echo  2. Lancement automatique au demarrage de Windows
echo     -^> L'application se lancera toute seule
echo        quand vous allumez l'ordinateur
echo.
echo Pour DESACTIVER le lancement automatique :
echo  - Appuyez sur Windows + R
echo  - Tapez : shell:startup
echo  - Supprimez le raccourci "Kyaf Edu Gabon"
echo.
echo ========================================
pause

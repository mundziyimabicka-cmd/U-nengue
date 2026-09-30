@echo off
title U nengue Gabon - Ecole Primaire
color 0A
cls
echo ========================================
echo    U NENGUE - Ecole Primaire
echo ========================================
echo.
echo Demarrage de l'application...
echo.

cd /d "%~dp0"

REM Verifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR: Python n'est pas installe ou pas dans le PATH.
    echo Installez Python depuis https://www.python.org/downloads/
    echo Cochez "Add Python to PATH" lors de l'installation.
    pause
    exit /b 1
)

REM Installer les dependances si besoin (silencieux)
python -m pip install flask flask-sqlalchemy reportlab Pillow --quiet 2>nul

echo.
echo L'application demarre...
echo.
echo Ouvrez votre navigateur sur :
echo.
echo    http://127.0.0.1:5000
echo.
echo Identifiant : admin
echo Mot de passe : admin123
echo.
echo NE FERMEZ PAS cette fenetre tant que vous utilisez l'application.
echo Pour arreter : appuyez sur Ctrl+C puis fermez la fenetre.
echo ========================================
echo.

REM Ouvrir le navigateur apres 2 secondes
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5000"

REM Lancer l'application
python app.py

pause

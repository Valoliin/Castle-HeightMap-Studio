@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Castle HeightMap Studio v4.1 - Installation Windows

echo ============================================================
echo        Castle HeightMap Studio v4.1 - Installation
echo ============================================================
echo.

set "PYTHON_CMD="
where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
    goto :python_found
)
where python >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

echo [ERREUR] Python n'a pas ete trouve.
echo Installe Python depuis https://www.python.org/downloads/windows/
echo et coche "Add Python to PATH".
pause
exit /b 1

:python_found
echo [OK] Python trouve :
%PYTHON_CMD% --version

echo.
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creation de l'environnement virtuel...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :error
) else (
    echo [1/3] Environnement .venv deja present.
)

echo [2/3] Mise a jour de pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :error

echo [3/3] Installation des dependances...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo ============================================================
echo                  INSTALLATION TERMINEE
echo ============================================================
echo.
choice /C ON /N /M "Lancer Castle HeightMap Studio maintenant ? [O/N] "
if errorlevel 2 goto :end
start "" ".venv\Scripts\pythonw.exe" "castle_heightmap_studio.py"
goto :end

:error
echo.
echo [ERREUR] L'installation a echoue.
echo Copie le contenu de cette fenetre pour le diagnostic.
pause
exit /b 1

:end
endlocal

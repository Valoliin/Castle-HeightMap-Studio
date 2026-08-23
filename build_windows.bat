@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Build Castle HeightMap Studio - Windows EXE

echo ============================================================
echo Castle HeightMap Studio - Build Windows EXE
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo L'environnement .venv n'existe pas.
    echo Lance d'abord install_windows.bat
    pause
    exit /b 1
)

echo Installation / mise a jour de PyInstaller...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller

if errorlevel 1 (
    echo [ERREUR] Installation de PyInstaller impossible.
    pause
    exit /b 1
)

echo.
echo Construction de CastleHeightMapStudio.exe...
".venv\Scripts\python.exe" "build_tools\build_pyinstaller.py"

if errorlevel 1 (
    echo.
    echo [ERREUR] Le build a echoue.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo BUILD TERMINE
echo ============================================================
echo.
echo EXE :
echo     dist\CastleHeightMapStudio.exe
echo.
pause

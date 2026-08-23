@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Castle HeightMap Studio v4.0 - Console
if not exist ".venv\Scripts\python.exe" (
    echo Lance d'abord install_windows.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "castle_heightmap_studio.py"
echo.
echo Le logiciel s'est ferme. Consulte aussi castle_heightmap.log si necessaire.
pause
endlocal

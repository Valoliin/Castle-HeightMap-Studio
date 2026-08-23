@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Castle HeightMap Studio n'est pas encore installe.
    echo Lance d'abord install_windows.bat
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "castle_heightmap_studio.py"
endlocal

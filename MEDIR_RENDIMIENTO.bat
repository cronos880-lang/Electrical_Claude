@echo off
setlocal
cd /d "%~dp0"
echo Medicion de rendimiento de Electrical Work (esquemas sinteticos).
echo Se abriran y cerraran ventanas varias veces. No toques el raton.
echo.
set "PYTHON_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 set "PYTHON_CMD=python"
%PYTHON_CMD% "%~dp0tests\bench_rendimiento.py" --json "%~dp0medicion_rendimiento.json"
echo.
echo Resultado guardado en medicion_rendimiento.json
pause

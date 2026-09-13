@echo off
REM Sentinel Omega — arranque para Windows (MSI Katana)
REM Uso: doble clic, o ponlo en el Programador de Tareas para auto-arranque.
REM Requiere haber corrido antes:
REM   python -m venv .venv
REM   .venv\Scripts\pip install -r sentinel_omega\requirements.txt
REM Y tus variables de entorno en deploy\.env (cargalas o ponlas de sistema).

cd /d "%~dp0\.."

:loop
del /f /q sentinel_omega\data\sentinel_omega.pid 2>nul
.venv\Scripts\python.exe sentinel_omega\launcher.py
echo Sentinel se detuvo. Reiniciando en 30s... (Ctrl+C para salir)
timeout /t 30 /nobreak >nul
goto loop

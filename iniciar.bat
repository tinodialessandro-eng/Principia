@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem --- Evita ejecutar desde dentro del .zip (carpeta temporal) ---
echo %~dp0 | find /i "\Temp\" >nul && (
  echo Primero extrae la carpeta completa del .zip y luego abre iniciar.bat desde la carpeta extraida.
  pause & exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul

rem --- Entorno unico "venv" (se crea una sola vez) ---
if not exist "venv\Scripts\python.exe" (
  if exist "venv" rmdir /s /q "venv"
  echo Creando el entorno por primera vez...
  set PY=python
  where python >nul 2>nul || set PY=py -3
  %PY% -m venv venv
  if errorlevel 1 (
    echo No encontre Python. Instalalo desde https://www.python.org marcando "Add Python to PATH".
    pause & exit /b 1
  )
  "venv\Scripts\python.exe" -m pip install --upgrade pip >nul
)

rem --- Instala/actualiza librerias solo si cambio requirements.txt ---
fc /b requirements.txt "venv\requisitos.txt" >nul 2>nul
if errorlevel 1 (
  echo Instalando librerias, puede tardar unos minutos...
  "venv\Scripts\python.exe" -m pip install -U -r requirements.txt
  if errorlevel 1 (
    echo Fallo la instalacion. Revisa tu conexion a internet y vuelve a abrir iniciar.bat.
    pause & exit /b 1
  )
  copy /y requirements.txt "venv\requisitos.txt" >nul
)

start "" cmd /c "timeout /t 3 >nul & start http://localhost:5000"
"venv\Scripts\python.exe" app.py
pause

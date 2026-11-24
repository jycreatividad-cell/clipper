@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Instala Python desde https://www.python.org/downloads/ marcando "Add to PATH" & pause & exit /b)
where ffmpeg >nul 2>nul || (echo Instalando ffmpeg... & winget install -e --id Gyan.FFmpeg & echo Cierra esta ventana y vuelve a abrir iniciar.bat & pause & exit /b)
where deno >nul 2>nul || (echo Instalando Deno, lo necesita yt-dlp para YouTube... & winget install -e --id DenoLand.Deno)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -q -U -r requirements.txt
python app.py
pause

@echo off
echo Starting Flask Server...
start "Flask Server" python app.py

rem Optionally wait a few seconds to ensure the Flask server starts up
timeout /t 5 /nobreak >nul

echo Starting ngrok tunnel...
start "ngrok" ngrok http --url=merely-big-falcon.ngrok-free.app 5000

pause
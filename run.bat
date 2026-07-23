@echo off
cd /d %~dp0
echo Launching ZERO Prediction Engine...
start "" "setup_scheduler.bat"
streamlit run app.py
pause

@echo off
<<<<<<< HEAD
cd /d "%~dp0"

if exist .venv goto ACTIVATED
echo Creating Python Virtual Environment (.venv)...
python -m venv .venv
echo Installing dependencies from requirements.txt...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
goto LAUNCH

:ACTIVATED
call .venv\Scripts\activate.bat

:LAUNCH
echo Launching ZERO Prediction Engine...
if exist "setup_scheduler.bat" (
    start "" "setup_scheduler.bat"
)
=======
cd /d %~dp0
echo Launching ZERO Prediction Engine...
start "" "setup_scheduler.bat"
>>>>>>> fd6d17459e62a7ed12ee718996c66c43ce394490
streamlit run app.py
pause

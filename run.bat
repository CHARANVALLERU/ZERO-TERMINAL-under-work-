@echo off
cd /d "%~dp0"

:: --- Runtime env defaults (no secrets required) ---
set "TOKENIZERS_PARALLELISM=false"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "STREAMLIT_SERVER_FILE_WATCHER_TYPE=poll"
:: Optional: uncomment and set your Hugging Face token for higher Hub rate limits
:: set "HF_TOKEN=hf_your_token_here"
:: If HF_TOKEN is already in your user/system environment, it is passed through automatically.

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
streamlit run app.py
pause

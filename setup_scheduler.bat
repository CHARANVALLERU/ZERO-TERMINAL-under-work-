@echo off
:: ============================================================
:: ZERO Engine — Task Scheduler Setup (Administrator Required)
:: 
:: This script registers a Windows Task Scheduler job that
:: runs the ZERO daily updater at 4:00 PM IST every day,
:: even when the user is logged out.
::
:: RUN THIS SCRIPT AS ADMINISTRATOR
:: ============================================================

echo ============================================================
echo    ZERO ENGINE — TASK SCHEDULER SETUP
echo ============================================================
echo.

:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script requires Administrator privileges.
    echo         Right-click and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

:: Get the directory where this script is located
set "ZERO_DIR=%~dp0"
set "ZERO_DIR=%ZERO_DIR:~0,-1%"

:: Detect Python path
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python is not found in PATH.
    echo         Please install Python or add it to your PATH.
    pause
    exit /b 1
)

for /f "delims=" %%i in ('where python') do set "PYTHON_PATH=%%i" & goto :found_python
:found_python

echo [INFO] ZERO Directory : %ZERO_DIR%
echo [INFO] Python Path    : %PYTHON_PATH%
echo [INFO] Script Path    : %ZERO_DIR%\engine\daily_updater.py
echo.

:: Delete existing task if it exists (for re-runs)
schtasks /delete /tn "ZERO_DailyUpdater" /f >nul 2>&1

:: Create the scheduled task
:: /SC DAILY        — Run every day
:: /ST 16:00        — At 4:00 PM (after market close at 3:30 PM IST)
:: /RL HIGHEST      — Run with highest privileges (admin)
:: /RU SYSTEM       — Run as SYSTEM user (works when logged out)
:: /F               — Force creation if task exists

schtasks /create ^
    /tn "ZERO_DailyUpdater" ^
    /tr "\"%PYTHON_PATH%\" \"%ZERO_DIR%\engine\daily_updater.py\"" ^
    /sc DAILY ^
    /st 16:00 ^
    /rl HIGHEST ^
    /ru SYSTEM ^
    /f

if %errorLevel% equ 0 (
    echo.
    echo ============================================================
    echo    SUCCESS! Task "ZERO_DailyUpdater" has been registered.
    echo.
    echo    Schedule : Daily at 4:00 PM IST
    echo    Runs as  : SYSTEM (works even when logged out)
    echo    Privilege: Highest (Administrator)
    echo.
    echo    You can verify in Task Scheduler:
    echo    1. Open "Task Scheduler" from Start Menu
    echo    2. Look for "ZERO_DailyUpdater" in the task list
    echo    3. Check "History" tab for execution logs
    echo.
    echo    Engine logs: %ZERO_DIR%\db\updater.log
    echo ============================================================
) else (
    echo.
    echo [ERROR] Failed to create scheduled task.
    echo         Make sure you are running as Administrator.
)

echo.
pause

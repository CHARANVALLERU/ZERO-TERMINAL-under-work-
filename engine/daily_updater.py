"""
ZERO Engine — Standalone Daily Updater

This script runs the complete daily prediction and training cycle
independently of the Streamlit app. It is designed to be invoked
by Windows Task Scheduler daily at 4:00 PM IST (after market close).

Functions performed:
1. Fetch actual OHLC data for today (if active trading day post 4:00 PM)
2. Update any unfulfilled feedback log entries
3. Generate fresh predictions for the next session (skipping weekends/holidays)
4. Log predictions for the next trading session to feedback database
5. Run auto-training / self-calibration engine
6. Refresh monthly prediction range config if stale

All activity is logged to db/updater.log for audit trail.
"""
import sys
import os
import datetime
import logging

# Ensure the project root is on the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import (
    is_trading_day as config_is_trading_day,
    is_market_closed_post_4pm,
    get_next_trading_day,
    now_ist
)
from engine.prediction_matrix import generate_prediction_matrix
from engine.learning_service import (
    fetch_daily_actuals,
    get_feedback_logs,
    update_feedback_logs,
    update_unfulfilled_feedback_logs,
    log_daily_feedback,
    auto_train_engine
)
from engine.prediction_ranges import get_range_config

# Configure logging
LOG_FILE = os.path.join(PROJECT_ROOT, 'db', 'updater.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('ZERO_UPDATER')


def run_daily_update():
    """Execute the full daily update cycle."""
    now = now_ist()
    today_str = now.strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info("ZERO DAILY UPDATER — CYCLE START")
    logger.info(f"Timestamp: {now.isoformat()}")
    logger.info("=" * 60)

    # Step 1 & 2: Update actual OHLC data for unfulfilled logs post 4:00 PM IST
    if is_market_closed_post_4pm(now):
        logger.info(f"Today ({today_str}) is an active trading day and market has opened & closed (post 4:00 PM IST).")
        try:
            logger.info("Updating unfulfilled feedback logs for completed sessions...")
            updated = update_unfulfilled_feedback_logs()
            if updated:
                logger.info("  Successfully updated actuals for completed trading sessions.")
            else:
                logger.info("  No pending unfulfilled logs to update.")
        except Exception as e:
            logger.error(f"Failed to update unfulfilled feedback logs: {e}")
    else:
        if not config_is_trading_day(now):
            logger.info(f"Today ({today_str}) is a market closed day (weekend or national holiday). Skipping prediction history update for today.")
        else:
            logger.info(f"Today ({today_str}) market has not reached post-4:00 PM close cycle yet (current time: {now.strftime('%H:%M')} IST). Skipping prediction history update.")

    # Step 3: Determine upcoming trading session date and generate fresh predictions
    next_session_date = get_next_trading_day(now).strftime("%Y-%m-%d")
    logger.info(f"Step 3: Generating prediction matrix for upcoming trading session: {next_session_date}...")
    try:
        matrix = generate_prediction_matrix()
        if 'error' in matrix:
            logger.error(f"  Prediction matrix error: {matrix['error']}")
        else:
            for idx_name in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
                if idx_name in matrix:
                    idx_data = matrix[idx_name]
                    logger.info(f"  {idx_name}: Open={idx_data.get('pred_open')}, "
                                f"High={idx_data.get('pred_high')}, Low={idx_data.get('pred_low')}")
    except Exception as e:
        logger.error(f"Failed to generate predictions: {e}")
        matrix = {}

    # Step 3b: Write the deterministic daily IC memo to the Obsidian vault
    logger.info("Step 3b: Writing daily IC memo to Obsidian vault...")
    try:
        if matrix and 'error' not in matrix:
            from engine.report_generator import memo_from_latest
            _debate = None
            try:
                _debate = (matrix.get('NIFTY 50') or {}).get('agent_debate')
            except Exception:
                _debate = None
            memo_path = memo_from_latest(matrix=matrix, debate=_debate)
            logger.info(f"  Daily IC memo written: {memo_path}")
        else:
            logger.info("  Skipped — no valid prediction matrix this cycle.")
    except Exception as e:
        logger.error(f"IC memo generation failed: {e}")

    # Step 4: Log daily predictions for the upcoming trading session
    logger.info(f"Step 4: Logging predictions for upcoming session {next_session_date}...")
    try:
        if matrix and 'error' not in matrix:
            log_daily_feedback(matrix, actual_data={}, reason="", target_date=next_session_date)
            logger.info(f"  Predictions for upcoming session ({next_session_date}) logged to feedback database.")
            logger.info("  Synced quantitative forecast bounds to Obsidian daily log.")
    except Exception as e:
        logger.error(f"Failed to log predictions: {e}")

    # Step 5: Auto-train engine
    logger.info("Step 5: Running auto-training cycle...")
    try:
        train_result = auto_train_engine(matrix)
        if train_result:
            logger.info(f"  Training result: {train_result.get('status', 'unknown')}")
            if train_result.get('results'):
                logger.info(f"  Details: {train_result['results']}")
        else:
            logger.info("  No training result returned.")
    except Exception as e:
        logger.error(f"Auto-train failed: {e}")

    # Step 5b: Retrain the adaptive calibration layer on the updated log
    logger.info("Step 5b: Retraining adaptive calibration layer...")
    try:
        from engine.calibrator import retrain_and_save
        cal = retrain_and_save(verbose=False)
        committed = sum(
            1 for legs in cal.metrics.values()
            for m in legs.values() if m.get("committed")
        )
        logger.info(f"  Calibrator retrained. Committed corrections: {committed} "
                    f"(trained_at={cal.trained_at})")
    except Exception as e:
        logger.error(f"Calibrator retrain failed: {e}")

    # Step 6: Refresh range config if stale
    logger.info("Step 6: Checking prediction range config freshness...")
    try:
        config = get_range_config()
        logger.info(f"  Range config last updated: {config.get('last_updated', 'N/A')}")
        for idx_name in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
            if idx_name in config:
                rc = config[idx_name]
                logger.info(f"  {idx_name}: Center={rc['center']}, "
                            f"Range=[{rc['max_low']}, {rc['max_high']}]")
    except Exception as e:
        logger.error(f"Range config check failed: {e}")

    logger.info("ZERO DAILY UPDATER — CYCLE COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_daily_update()


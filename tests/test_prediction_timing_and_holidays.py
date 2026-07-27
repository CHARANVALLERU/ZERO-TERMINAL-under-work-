"""
Unit tests for ZERO market schedule, national holidays, post-4 PM IST prediction history updates,
and upcoming trading session range forecasting.
"""
import unittest
import datetime
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import is_trading_day, get_next_trading_day, is_market_closed_post_4pm, NSE_HOLIDAYS
from engine.learning_service import fetch_daily_actuals, log_daily_feedback, update_unfulfilled_feedback_logs

class TestPredictionTimingAndHolidays(unittest.TestCase):

    def test_weekend_and_holiday_detection(self):
        # Saturday test
        sat = datetime.datetime(2026, 7, 25, 12, 0) # Saturday
        self.assertFalse(is_trading_day(sat))

        # Known NSE Holiday test (Independence Day 2026-08-15)
        holiday = datetime.datetime(2026, 8, 15, 10, 0)
        self.assertFalse(is_trading_day(holiday))

        # Valid trading day (Wednesday 2026-07-22)
        trading_day = datetime.datetime(2026, 7, 22, 10, 0)
        self.assertTrue(is_trading_day(trading_day))

    def test_get_next_trading_day(self):
        # On Friday after close (16:30), next trading day should be Monday
        fri_afternoon = datetime.datetime(2026, 7, 24, 16, 30)
        next_day = get_next_trading_day(fri_afternoon)
        self.assertEqual(next_day, datetime.date(2026, 7, 27))

        # On Independence Day 2026-08-15 (Saturday), next trading day should be Monday 2026-08-17
        indep_day = datetime.datetime(2026, 8, 15, 10, 0)
        next_day = get_next_trading_day(indep_day)
        self.assertEqual(next_day, datetime.date(2026, 8, 17))

    def test_post_4pm_timing_gatekeeper(self):
        # Trading day at 14:30 IST -> post 4 PM should be False
        day_pre_4pm = datetime.datetime(2026, 7, 22, 14, 30)
        self.assertFalse(is_market_closed_post_4pm(day_pre_4pm))

        # Trading day at 16:15 IST -> post 4 PM should be True
        day_post_4pm = datetime.datetime(2026, 7, 22, 16, 15)
        self.assertTrue(is_market_closed_post_4pm(day_post_4pm))

        # Saturday at 17:00 IST -> post 4 PM should be False (not a trading day)
        sat_post_4pm = datetime.datetime(2026, 7, 25, 17, 0)
        self.assertFalse(is_market_closed_post_4pm(sat_post_4pm))

    def test_fetch_actuals_skips_non_trading_days(self):
        # Trying to fetch actuals for a holiday or weekend date should return empty dict
        actuals_weekend = fetch_daily_actuals(target_date="2026-07-25")
        self.assertEqual(actuals_weekend, {})

    def test_log_daily_feedback_skips_holidays(self):
        dummy_matrix = {
            "NIFTY 50": {"pred_open": 24000, "pred_high": 24200, "pred_low": 23800}
        }
        # Explicitly logging for a holiday date should return False and skip
        res = log_daily_feedback(dummy_matrix, target_date="2026-08-15")
        self.assertFalse(res)

if __name__ == "__main__":
    unittest.main()

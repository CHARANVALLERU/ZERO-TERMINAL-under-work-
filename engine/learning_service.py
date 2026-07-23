import json
import os
import datetime
from config import ALPHA, BETA, GAMMA

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), '..', 'db', 'feedback_log.json')

def fetch_daily_actuals(target_date: str = None):
    """
    Fetches the actual OHLC values for NIFTY 50, BANKNIFTY, and SENSEX using yfinance.
    If target_date (YYYY-MM-DD) is provided, fetches for that date; otherwise defaults to today IST.
    Only returns actuals if target_date was an active trading session (not weekend/holiday)
    and if today's market session has completed (post 4:00 PM IST for today's date).
    """
    from config import is_trading_day, is_market_closed_post_4pm, now_ist
    import yfinance as yf  # lazy: keep local-log operations importable offline

    now = now_ist()
    today_str = now.strftime("%Y-%m-%d")
    
    if target_date is None:
        target_date = today_str

    try:
        t_dt = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        t_dt = now.date()

    # Do NOT fetch or log actuals on non-trading days (weekends or national holidays)
    if not is_trading_day(t_dt):
        return {}

    # If target date is today, only fetch actuals if market has closed post 4:00 PM IST
    if target_date == today_str and not is_market_closed_post_4pm(now):
        return {}

    tickers = {
        "NIFTY 50": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "SENSEX": "^BSESN"
    }
    actuals = {}
    for idx, ticker in tickers.items():
        try:
            data = yf.Ticker(ticker)
            if target_date == today_str:
                df = data.history(period="1d")
            else:
                end_dt = (t_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                df = data.history(start=target_date, end=end_dt)

            if not df.empty:
                latest = df.iloc[-1]
                actuals[idx] = {
                    "open": round(float(latest['Open']), 2),
                    "high": round(float(latest['High']), 2),
                    "low": round(float(latest['Low']), 2),
                    "close": round(float(latest['Close']), 2)
                }
            else:
                actuals[idx] = {"open": "N/A", "high": "N/A", "low": "N/A", "close": "N/A"}
        except Exception as e:
            print(f"Error fetching {idx} actuals for {target_date}: {e}")
            actuals[idx] = {"open": "N/A", "high": "N/A", "low": "N/A", "close": "N/A"}
    return actuals

def log_daily_feedback(prediction_data, actual_data=None, reason="", target_date=None):
    """
    Logs prediction vs actual results to the local database, deduplicated by day and index.
    
    Updated rules:
    - Never logs or updates prediction history on national holidays or weekends.
    - If market is closed post 4:00 PM IST or today is a non-trading day, default target_date
      is automatically assigned to the upcoming trading session (get_next_trading_day()).
    """
    from config import is_trading_day, is_market_closed_post_4pm, get_next_trading_day, now_ist

    actual_data = actual_data or {}
    now = now_ist()
    today_str = now.strftime("%Y-%m-%d")

    if not target_date:
        if is_market_closed_post_4pm(now) or not is_trading_day(now):
            target_date = get_next_trading_day(now).strftime("%Y-%m-%d")
        else:
            target_date = today_str

    try:
        t_dt = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        t_dt = now.date()

    # Skip logging if target date is a weekend or national holiday
    if not is_trading_day(t_dt):
        print(f"Skipping prediction log entry: {target_date} is a market closed day (weekend/holiday).")
        return False

    try:
        if os.path.exists(FEEDBACK_FILE) and os.path.getsize(FEEDBACK_FILE) > 0:
            with open(FEEDBACK_FILE, 'r') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    logs = []
        else:
            logs = []
            
        index_names = ["NIFTY 50", "BANKNIFTY", "SENSEX"]

        # Detect format: new per-index format has index names as top-level keys
        is_new_format = any(idx_name in prediction_data for idx_name in index_names)

        for idx_name in index_names:
            if is_new_format:
                idx_pred_data = prediction_data.get(idx_name, {})
                if 'error' in idx_pred_data:
                    continue
                idx_pred = {
                    "pred_open": idx_pred_data.get('pred_open', 0),
                    "pred_high": idx_pred_data.get('pred_high', 0),
                    "pred_low": idx_pred_data.get('pred_low', 0),
                }
                raw_inputs = idx_pred_data
            else:
                multipliers = {"NIFTY 50": 1.0, "BANKNIFTY": 2.41, "SENSEX": 3.22}
                mult = multipliers[idx_name]
                idx_pred = {
                    "pred_open": round(prediction_data.get('pred_open', 0) * mult, 2),
                    "pred_high": round(prediction_data.get('pred_high', 0) * mult, 2),
                    "pred_low": round(prediction_data.get('pred_low', 0) * mult, 2),
                }
                raw_inputs = prediction_data
            
            idx_actual = actual_data.get(idx_name, {"open": "N/A", "high": "N/A", "low": "N/A", "close": "N/A"})
            
            existing_entry = next((log for log in logs if log.get('date') == target_date and log.get('index') == idx_name), None)
            
            if existing_entry:
                if idx_actual.get('open') != "N/A" and idx_actual.get('open') != 0:
                    existing_entry['actual'] = idx_actual
                if reason:
                    existing_entry['reason'] = reason
            else:
                entry = {
                    "id": f"{target_date}_{idx_name.replace(' ', '_')}",
                    "date": target_date,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "index": idx_name,
                    "predicted": idx_pred,
                    "actual": idx_actual,
                    "reason": reason,
                    "raw_inputs": raw_inputs,
                    "current_params": {
                        "ALPHA": ALPHA,
                        "BETA": BETA,
                        "GAMMA": GAMMA
                    }
                }
                logs.append(entry)
        
        with open(FEEDBACK_FILE, 'w') as f:
            json.dump(logs, f, indent=4)
            
        # ── Sync predictions to Obsidian daily log ──
        try:
            from engine.obsidian_sync import sync_forecast_to_obsidian
            sync_forecast_to_obsidian(prediction_data, target_date)
        except Exception as oe:
            print(f"Error syncing forecasts to Obsidian: {oe}")
            
        return True
    except Exception as e:
        print(f"Error logging feedback: {e}")
        return False

def get_feedback_logs():
    """Returns all logged feedback."""
    if not os.path.exists(FEEDBACK_FILE) or os.path.getsize(FEEDBACK_FILE) == 0:
        return []
    try:
        with open(FEEDBACK_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def update_feedback_logs(new_logs):
    """Overwrite the feedback_log.json with new list of logs from the editor."""
    try:
        with open(FEEDBACK_FILE, 'w') as f:
            json.dump(new_logs, f, indent=4)
        return True
    except Exception as e:
        print(f"Error updating logs: {e}")
        return False

def update_unfulfilled_feedback_logs():
    """
    Scans feedback logs and updates missing actuals for past trading days or today post 4:00 PM IST.
    Skips non-trading days (holidays/weekends).
    """
    from config import is_trading_day, is_market_closed_post_4pm, now_ist
    logs = get_feedback_logs()
    if not logs:
        return False

    now = now_ist()
    today_str = now.strftime("%Y-%m-%d")
    updated = False

    unfulfilled_dates = set()
    for log in logs:
        log_date = log.get('date')
        if not log_date:
            continue
        try:
            d_dt = datetime.datetime.strptime(log_date, "%Y-%m-%d").date()
        except Exception:
            continue
        if not is_trading_day(d_dt):
            continue

        if log_date < today_str or (log_date == today_str and is_market_closed_post_4pm(now)):
            if isinstance(log.get('actual'), dict) and log['actual'].get('open') == 'N/A':
                unfulfilled_dates.add(log_date)

    if not unfulfilled_dates:
        return False

    for u_date in unfulfilled_dates:
        fetched = fetch_daily_actuals(target_date=u_date)
        if fetched:
            for log in logs:
                if log.get('date') == u_date:
                    idx = log.get('index')
                    if idx in fetched and fetched[idx].get('open') != 'N/A':
                        log['actual'] = fetched[idx]
                        updated = True

    if updated:
        update_feedback_logs(logs)

    return updated

def calculate_engine_accuracy():
    """
    Computes accuracy metrics based on previous logs.
    Returns a dict of error percentages.
    """
    logs = get_feedback_logs()
    if not logs:
        return None
        
    metrics = {
        "dates": [],
        "open_error": [],
        "high_error": [],
        "low_error": []
    }
    
    date_groups = {}
    for entry in logs:
        date = entry.get('date')
        if date not in date_groups:
            date_groups[date] = []
        date_groups[date].append(entry)
        
    for date, entries in date_groups.items():
        total_open_err = 0
        total_high_err = 0
        total_low_err = 0
        valid_count = 0
        
        for entry in entries:
            p = entry.get('predicted', {})
            a = entry.get('actual', {})
            
            if not isinstance(a, dict) or str(a.get('open')) == "N/A" or not a.get('open') or float(a.get('open')) <= 0:
                continue
                
            p_open = p.get('pred_open', 0)
            p_high = p.get('pred_high', 0)
            p_low = p.get('pred_low', 0)
            
            a_open = float(a.get('open', 0))
            a_high = float(a.get('high', 0))
            a_low = float(a.get('low', 0))
            
            if a_open > 0 and a_high > 0 and a_low > 0:
                total_open_err += abs(p_open - a_open) / a_open * 100
                total_high_err += abs(p_high - a_high) / a_high * 100
                total_low_err += abs(p_low - a_low) / a_low * 100
                valid_count += 1
                
        if valid_count > 0:
            metrics['dates'].append(date)
            metrics['open_error'].append(total_open_err / valid_count)
            metrics['high_error'].append(total_high_err / valid_count)
            metrics['low_error'].append(total_low_err / valid_count)
        
    return metrics

def suggest_calibration():
    """
    Analyzes historical gaps and suggests better ALPHA/BETA.
    Requires at least 3-5 days of data for meaningful results.
    """
    logs = get_feedback_logs()
    if len(logs) < 3:
        return None
        
    best_alpha, best_beta = ALPHA, BETA
    min_mae = float('inf')
    
    # Simple Grid Search for local optimization
    for a in [x * 0.05 for x in range(10, 21)]: # 0.5 to 1.0
        for b in [x * 0.05 for x in range(0, 11)]: # 0.0 to 0.5
            total_error = 0
            count = 0
            for entry in logs:
                actual = entry.get('actual', {})
                if not isinstance(actual, dict) or str(actual.get('open')) == "N/A" or not actual.get('open') or float(actual.get('open')) <= 0:
                    continue
                
                raw_inputs = entry.get('raw_inputs', {})
                idx_name = entry.get('index', 'NIFTY 50')
                
                gift_price = raw_inputs.get('gift_nifty') or 0
                prev_close = raw_inputs.get('prev_close') or 0
                gift_premium = gift_price - prev_close
                adr_delta = raw_inputs.get('adr_delta') or 0
                
                calc_gap = (a * gift_premium) + (b * adr_delta)
                
                prev_close_val = prev_close
                actual_gap = float(actual.get('open', 0)) - prev_close_val
                
                total_error += abs(calc_gap - actual_gap)
                count += 1
            
            if count > 0:
                mae = total_error / count
                if mae < min_mae:
                    min_mae = mae
                    best_alpha, best_beta = a, b
                    
    return {
        "current": {"ALPHA": ALPHA, "BETA": BETA},
        "suggested": {"ALPHA": round(best_alpha, 2), "BETA": round(best_beta, 2)},
        "reduction_potential": f"{min_mae:.2f} pts avg error"
    }

def auto_train_engine(current_matrix):
    """
    Automated core process running daily post-market to fetch actuals, define narrative,
    update historical logs, and self-train config parameters.
    
    Supports both new per-index matrix format and legacy format.
    """
    from data.market_news import get_global_news, analyze_sentiment
    import re

    # 1. Fetch Actuals
    actuals = fetch_daily_actuals()
    
    # 2. Extract News Narrative
    news = get_global_news()
    sentiment_result = analyze_sentiment(news)
    
    # Handle both old float and new dict sentiment format
    if isinstance(sentiment_result, dict):
        sentiment = sentiment_result.get('score', 0)
    else:
        sentiment = sentiment_result
    
    # News may be list[dict] (new format) or list[str] (legacy); flatten to titles.
    _titles = [n.get("title", "") if isinstance(n, dict) else str(n) for n in (news or [])]
    news_text = " ".join(_titles).lower()
    bullish = any(w in news_text for w in ['growth', 'recovery', 'stimulus', 'rate cut', 'surge', 'rally'])
    bearish = any(w in news_text for w in ['war', 'conflict', 'inflation', 'rate hike', 'recession', 'crash', 'sell-off'])
    
    if sentiment > 0.3 or bullish:
        reason = "Automated Core Update: Bullish macroeconomic tilt pushed order flow upwards against algorithmic base."
    elif sentiment < -0.3 or bearish:
        reason = "Automated Core Update: Bearish macro factors triggered systemic sell-offs/liquidations."
    else:
        reason = "Automated Core Update: Market aligned cleanly with predictive envelopes amidst neutral global sentiment."
        
    # 3. Log Data
    # Only try to train if we successfully fetched actual data for at least NIFTY
    if actuals.get('NIFTY 50', {}).get('open') != "N/A":
        log_daily_feedback(current_matrix, actuals, reason)
        
        # 4. Self-Calibrate
        calc = suggest_calibration()
        if calc:
            sug_alpha = calc['suggested']['ALPHA']
            sug_beta = calc['suggested']['BETA']
            cur_alpha = calc['current']['ALPHA']
            cur_beta = calc['current']['BETA']
            
            if (sug_alpha != cur_alpha) or (sug_beta != cur_beta):
                # Write directly to config.py
                config_path = os.path.join(os.path.dirname(__file__), '..', 'config.py')
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        content = f.read()
                    
                    content = re.sub(r'ALPHA\s*=\s*[0-9.]+', f'ALPHA = {sug_alpha}', content)
                    content = re.sub(r'BETA\s*=\s*[0-9.]+', f'BETA = {sug_beta}', content)
                    
                    with open(config_path, 'w') as f:
                        f.write(content)
                
                return {"status": "trained", "results": calc}
                
        return {"status": "holding", "results": calc if calc else "Insufficient data"}
    
    return {"status": "failed", "results": "No actuals fetched. Data might not be settled."}

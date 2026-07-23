import sqlite3
import json
import os
import datetime
import pandas as pd
from config import DB_PATH
import os

def init_db():
    """Initialize the SQLite database with required tables."""
    # Ensure directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Predictions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        symbol TEXT,
        pred_open REAL,
        pred_high REAL,
        pred_low REAL,
        pred_close REAL,
        actual_open REAL,
        actual_high REAL,
        actual_low REAL,
        actual_close REAL,
        confidence REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Global Signals table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS global_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        vix REAL,
        sp500_change REAL,
        nasdaq_change REAL,
        gift_nifty_premium REAL,
        adr_weighted_delta REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Model Registry table — one row per (symbol, target, version)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS model_registry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        registered_at TEXT,
        symbol TEXT,
        target TEXT,
        version TEXT,
        walk_forward_mae REAL,
        baseline_mae REAL,
        n_train_rows INTEGER,
        features TEXT,
        artifact_path TEXT,
        is_active INTEGER DEFAULT 1
    )
    ''')

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

def save_prediction(data):
    """Save a prediction record."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.DataFrame([data])
    df.to_sql('predictions', conn, if_exists='append', index=False)
    conn.close()

def get_predictions(limit=10):
    """Fetch recent predictions."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM predictions ORDER BY id DESC LIMIT {limit}", conn)
    conn.close()
    return df


def register_model(symbol, target, version, walk_forward_mae, baseline_mae,
                   n_train_rows, features, artifact_path):
    """
    Record a newly trained XGB head in the SQLite registry. Marks prior
    entries for the same (symbol, target) as inactive so there is one
    canonical active head per target.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE model_registry SET is_active = 0 WHERE symbol = ? AND target = ?",
        (symbol, target),
    )
    cur.execute(
        """
        INSERT INTO model_registry
        (registered_at, symbol, target, version, walk_forward_mae, baseline_mae,
         n_train_rows, features, artifact_path, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            datetime.datetime.now().isoformat(),
            symbol,
            target,
            version,
            float(walk_forward_mae),
            float(baseline_mae),
            int(n_train_rows),
            json.dumps(features),
            artifact_path,
        ),
    )
    conn.commit()
    conn.close()


def get_latest_model(symbol, target):
    """Return the active model-registry row, or None if not present."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT * FROM model_registry
        WHERE symbol = ? AND target = ? AND is_active = 1
        ORDER BY registered_at DESC LIMIT 1
        """,
        conn,
        params=(symbol, target),
    )
    conn.close()
    if df.empty:
        return None
    rec = df.iloc[0].to_dict()
    try:
        rec['features'] = json.loads(rec['features'])
    except (TypeError, ValueError):
        pass
    return rec


def list_active_models():
    """Return all currently-active models, one row per (symbol, target)."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM model_registry WHERE is_active = 1 ORDER BY registered_at DESC",
        conn,
    )
    conn.close()
    return df


if __name__ == "__main__":
    init_db()

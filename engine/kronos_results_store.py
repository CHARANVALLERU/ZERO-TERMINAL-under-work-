"""
Kronos prediction history store for ZERO.

Cloned from the Kronos webui persistence layer (``webui/app.py`` ->
``save_prediction_results``), which dumps every forecast to
``prediction_<YYYYmmdd_HHMMSS>.json`` inside a flat results directory.
This module keeps that simple file-per-prediction design but hardens it
for terminal use:

  * files carry a short unique id so same-second saves never collide,
  * the store prunes itself (oldest first) beyond ``MAX_FILES`` entries,
  * every public function is a no-op on failure -- it never raises,
  * listing tolerates malformed / foreign files left in the directory.

Storage directory (created on demand):
    <project root>/db/kronos_predictions/
overridable via the ``KRONOS_PREDICTIONS_DIR`` environment variable
(read at call time, so tests can point the store at a temp dir).

Stdlib only: json, os, time, uuid, glob.
"""

import glob
import json
import os
import time
import uuid

__all__ = [
    "save_prediction",
    "list_predictions",
    "load_prediction",
    "delete_prediction",
    "clear_all",
    "MAX_FILES",
]

# Hard cap on stored prediction files; oldest are pruned beyond this.
MAX_FILES = 200

_ENV_VAR = "KRONOS_PREDICTIONS_DIR"
_FILE_PREFIX = "prediction_"
_FILE_GLOB = _FILE_PREFIX + "*.json"


# --------------------------------------------------------------------------
# directory helpers
# --------------------------------------------------------------------------

def _default_dir():
    """<project root>/db/kronos_predictions, derived from this file's location."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "db", "kronos_predictions")


def _store_dir():
    """Resolve the active storage directory (env override wins). Never raises."""
    try:
        override = os.environ.get(_ENV_VAR, "").strip()
        return override if override else _default_dir()
    except Exception:
        return _default_dir()


def _ensure_dir():
    """Create the storage dir on demand. Returns the path or '' on failure."""
    path = _store_dir()
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        return ""


def _prediction_files(directory):
    """All prediction JSON paths in *directory*, oldest first (mtime, then name)."""
    try:
        paths = glob.glob(os.path.join(directory, _FILE_GLOB))
    except Exception:
        return []

    def _key(p):
        try:
            mtime = os.path.getmtime(p)
        except Exception:
            mtime = 0.0
        return (mtime, os.path.basename(p))

    try:
        return sorted(paths, key=_key)
    except Exception:
        return paths


def _read_json(path):
    """Parse a JSON file; returns the object or None on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _find_file(pred_id, directory=None):
    """Locate the file for *pred_id*: by filename suffix first, then by content."""
    if not pred_id:
        return None
    directory = directory or _store_dir()
    if not os.path.isdir(directory):
        return None
    pid = str(pred_id)

    # Fast path: our own files embed the id in the filename.
    try:
        hits = glob.glob(os.path.join(directory, _FILE_PREFIX + "*_" + pid + ".json"))
        if hits:
            return hits[0]
    except Exception:
        pass

    # Slow path: foreign/legacy files -- match on the stored 'id' field.
    for path in _prediction_files(directory):
        record = _read_json(path)
        if isinstance(record, dict) and str(record.get("id", "")) == pid:
            return path
    return None


def _prune(directory):
    """Delete oldest files beyond MAX_FILES. Best effort, never raises."""
    try:
        limit = int(MAX_FILES)
    except Exception:
        limit = 200
    if limit <= 0:
        return
    try:
        paths = _prediction_files(directory)
        excess = len(paths) - limit
        for path in paths[:max(0, excess)]:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception:
        pass


# --------------------------------------------------------------------------
# tolerant field extraction (supports both ZERO records and the upstream
# webui schema: prediction_params / input_data_summary / prediction_results)
# --------------------------------------------------------------------------

def _get_num(value):
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except Exception:
        return None


def _extract_pred_len(record):
    for key in ("pred_len", "prediction_length", "horizon"):
        try:
            if record.get(key) is not None:
                return int(record[key])
        except Exception:
            pass
    try:
        params = record.get("prediction_params")
        if isinstance(params, dict) and params.get("pred_len") is not None:
            return int(params["pred_len"])
    except Exception:
        pass
    for key in ("predictions", "prediction_results", "forecast"):
        try:
            rows = record.get(key)
            if isinstance(rows, (list, tuple)) and rows:
                return len(rows)
        except Exception:
            pass
    return None


def _extract_last_close(record):
    value = _get_num(record.get("last_close"))
    if value is not None:
        return value
    try:
        summary = record.get("input_data_summary")
        if isinstance(summary, dict):
            last_values = summary.get("last_values")
            if isinstance(last_values, dict):
                return _get_num(last_values.get("close"))
    except Exception:
        pass
    return None


def _extract_predicted_close(record):
    value = _get_num(record.get("predicted_close"))
    if value is not None:
        return value
    for key in ("predictions", "prediction_results", "forecast"):
        try:
            rows = record.get(key)
            if isinstance(rows, (list, tuple)) and rows:
                tail = rows[-1]
                if isinstance(tail, dict):
                    return _get_num(tail.get("close"))
                return _get_num(tail)
        except Exception:
            pass
    return None


def _extract_direction(record, last_close, predicted_close):
    direction = record.get("direction")
    if isinstance(direction, str) and direction:
        return direction
    if last_close is None or predicted_close is None:
        return None
    if predicted_close > last_close:
        return "up"
    if predicted_close < last_close:
        return "down"
    return "flat"


def _summarize(path, record):
    """Lightweight listing entry for one stored prediction."""
    if not isinstance(record, dict):
        record = {}
    last_close = _extract_last_close(record)
    predicted_close = _extract_predicted_close(record)
    return {
        "id": record.get("id"),
        "created_at": record.get("created_at") or record.get("timestamp"),
        "symbol": record.get("symbol"),
        "interval": record.get("interval") or record.get("timeframe"),
        "pred_len": _extract_pred_len(record),
        "last_close": last_close,
        "predicted_close": predicted_close,
        "direction": _extract_direction(record, last_close, predicted_close),
        "path": path,
    }


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def save_prediction(record):
    """Persist *record* (a dict) as a new prediction JSON file.

    Injects ``id`` (short uuid) and ``created_at`` (UTC ISO-8601), writes
    ``prediction_<YYYYmmdd_HHMMSS>_<id>.json`` (non-serializable values fall
    back to ``str``), prunes the oldest files beyond ``MAX_FILES``.

    Returns the full file path, or ``''`` on any failure. Never raises.
    """
    try:
        if not isinstance(record, dict):
            return ""
        directory = _ensure_dir()
        if not directory:
            return ""

        pred_id = uuid.uuid4().hex[:8]
        now = time.time()
        payload = dict(record)
        payload["id"] = pred_id
        payload["created_at"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

        stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime(now))
        filename = "%s%s_%s.json" % (_FILE_PREFIX, stamp, pred_id)
        path = os.path.join(directory, filename)

        # Write via temp file + atomic replace so listers never see half a file.
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_path, path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return ""

        _prune(directory)
        return path
    except Exception:
        return ""


def list_predictions(limit=50):
    """Newest-first lightweight summaries of stored predictions.

    Each entry: id, created_at, symbol, interval, pred_len, last_close,
    predicted_close, direction, path. Malformed or foreign files in the
    directory are skipped. Never raises; returns ``[]`` on any failure.
    """
    try:
        directory = _store_dir()
        if not os.path.isdir(directory):
            return []
        summaries = []
        for path in reversed(_prediction_files(directory)):  # newest first
            record = _read_json(path)
            if not isinstance(record, dict):
                continue  # tolerate malformed / non-dict files
            summaries.append(_summarize(path, record))
        if limit is not None:
            try:
                cap = int(limit)
            except Exception:
                cap = 50
            if cap >= 0:
                summaries = summaries[:cap]
        return summaries
    except Exception:
        return []


def load_prediction(pred_id):
    """Full stored record for *pred_id*, or ``None`` if missing/unreadable."""
    try:
        path = _find_file(pred_id)
        if not path:
            return None
        record = _read_json(path)
        return record if isinstance(record, dict) else None
    except Exception:
        return None


def delete_prediction(pred_id):
    """Delete the stored prediction for *pred_id*. True on success."""
    try:
        path = _find_file(pred_id)
        if not path:
            return False
        os.remove(path)
        return True
    except Exception:
        return False


def clear_all():
    """Delete every stored prediction file. Returns the number removed."""
    removed = 0
    try:
        directory = _store_dir()
        if not os.path.isdir(directory):
            return 0
        for path in _prediction_files(directory):
            try:
                os.remove(path)
                removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed

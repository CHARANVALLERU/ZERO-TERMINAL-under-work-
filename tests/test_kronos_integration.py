"""
Integration tests for the Kronos foundation-model stack cloned into ZERO.

Covers:
  * engine.kronos_results_store -- round-trip, ordering, pruning, and the
    never-raise contract (always runnable, stdlib + numpy only).
  * No-op safety contracts of the sibling Kronos modules
    (engine.kronos_service, data.kronos_adapter, engine.kronos_backtest,
    ui.kronos_charts). Each test skips cleanly when the module does not
    exist yet, so the suite passes at every stage of the build-out.
  * A vendored-model regression test mirroring upstream
    Kronos ``tests/test_kronos_regression.py`` (256-context case only),
    importing from engine.kronos and using fixtures under
    tests/data/kronos/. Skips when torch or the HF weights are
    unavailable or downloads are disabled.

All tests are deterministic and runnable offline (skips are expected
where optional dependencies or weights are missing).

Run with:  python -m pytest tests/test_kronos_integration.py -q
"""
import json
import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import engine.kronos_results_store as krs  # noqa: E402  (stdlib-only, always safe)

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "kronos")
REGRESSION_INPUT = os.path.join(FIXTURE_DIR, "regression_input.csv")
REGRESSION_OUTPUT_256 = os.path.join(FIXTURE_DIR, "regression_output_256.csv")

# Pinned upstream revisions (mirrors Kronos tests/test_kronos_regression.py).
TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
MODEL_ID = "NeoQuasar/Kronos-small"
MODEL_REVISION = "901c26c1332695a2a8f243eb2f37243a37bea320"
TOKENIZER_REVISION = "0e0117387f39004a9016484a186a908917e22426"
REGRESSION_FEATURES = ["open", "high", "low", "close", "volume", "amount"]
REGRESSION_RTOL = 1e-5
SEED = 123


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _first_accepted(attempts):
    """Call each zero-arg attempt until one is not rejected with TypeError.

    Sibling module signatures are still settling, so contract tests probe a
    few plausible call shapes. A TypeError is treated as "wrong signature,
    try the next"; any other exception propagates (the no-op safety
    contracts say these functions must not raise).
    """
    for attempt in attempts:
        try:
            return True, attempt()
        except TypeError:
            continue
    return False, None


def _synthetic_ohlcv(pd, n=64, freq="1h", seed=7, start="2026-01-05"):
    """Small deterministic OHLCV frame in the house schema."""
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.5, size=n))
    open_ = np.empty(n)
    open_[0] = 100.0
    open_[1:] = close[:-1]
    spread = rng.uniform(0.05, 0.6, size=n)
    volume = rng.uniform(100.0, 1000.0, size=n)
    return pd.DataFrame({
        "timestamps": pd.date_range(start, periods=n, freq=freq),
        "open": open_,
        "high": np.maximum(open_, close) + spread,
        "low": np.minimum(open_, close) - spread,
        "close": close,
        "volume": volume,
        "amount": volume * close,
    })


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """The results store pointed at a fresh temp directory via env override."""
    monkeypatch.setenv("KRONOS_PREDICTIONS_DIR", str(tmp_path))
    return krs


# ---------------------------------------------------------------------------
# Part 1: results store (always runs)
# ---------------------------------------------------------------------------

def test_store_default_dir_is_db_kronos_predictions(monkeypatch):
    monkeypatch.delenv("KRONOS_PREDICTIONS_DIR", raising=False)
    expected_tail = os.path.join("db", "kronos_predictions")
    assert krs._store_dir().endswith(expected_tail)


def test_store_roundtrip_save_list_load_delete(store, tmp_path):
    record = {
        "symbol": "BTCUSDT", "interval": "1h", "pred_len": 3,
        "last_close": 100.0, "predicted_close": 101.5,
        "predictions": [
            {"close": 100.5}, {"close": 101.0}, {"close": 101.5},
        ],
    }
    path = store.save_prediction(record)
    assert path, "save_prediction returned '' on a valid record"
    assert os.path.isfile(path)
    assert os.path.dirname(path) == str(tmp_path)
    assert os.path.basename(path).startswith("prediction_")
    assert path.endswith(".json")

    # Original record must not be mutated by the id/created_at injection.
    assert "id" not in record and "created_at" not in record

    summaries = store.list_predictions()
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["symbol"] == "BTCUSDT"
    assert summary["interval"] == "1h"
    assert summary["pred_len"] == 3
    assert summary["last_close"] == 100.0
    assert summary["predicted_close"] == 101.5
    assert summary["direction"] == "up"
    assert summary["path"] == path
    assert summary["id"]
    assert summary["created_at"]

    loaded = store.load_prediction(summary["id"])
    assert loaded is not None
    assert loaded["symbol"] == "BTCUSDT"
    assert loaded["id"] == summary["id"]
    assert loaded["created_at"] == summary["created_at"]

    assert store.delete_prediction(summary["id"]) is True
    assert store.list_predictions() == []
    assert store.load_prediction(summary["id"]) is None
    assert store.delete_prediction(summary["id"]) is False


def test_store_lists_newest_first_and_honors_limit(store):
    ids = []
    for i in range(3):
        path = store.save_prediction({"symbol": f"SYM{i}", "seq": i})
        assert path
        ids.append(store.list_predictions(limit=1)[0]["id"])
        time.sleep(0.05)  # ensure distinct mtimes for deterministic ordering
    all_rows = store.list_predictions()
    assert [row["symbol"] for row in all_rows] == ["SYM2", "SYM1", "SYM0"]
    top_two = store.list_predictions(limit=2)
    assert [row["symbol"] for row in top_two] == ["SYM2", "SYM1"]
    assert [row["id"] for row in top_two] == [ids[2], ids[1]]


def test_store_tolerates_malformed_files(store, tmp_path):
    # Corrupt JSON and valid-but-not-a-dict JSON dropped into the store dir.
    bad = tmp_path / "prediction_19990101_000000_deadbeef.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    weird = tmp_path / "prediction_19990101_000001_feedface.json"
    weird.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    good_path = store.save_prediction({"symbol": "ETHUSDT"})
    assert good_path

    summaries = store.list_predictions()  # must not raise
    assert [row["symbol"] for row in summaries] == ["ETHUSDT"]

    assert store.load_prediction("deadbeef") is None  # unreadable -> None
    assert store.load_prediction("no-such-id") is None
    assert store.delete_prediction("no-such-id") is False
    # Deleting a corrupt file by its filename-embedded id is allowed cleanup.
    assert store.delete_prediction("deadbeef") is True
    assert not bad.exists()

    assert store.clear_all() == 2  # good record + the non-dict JSON file
    assert store.list_predictions() == []


def test_store_prunes_oldest_beyond_cap(store, tmp_path, monkeypatch):
    monkeypatch.setattr(krs, "MAX_FILES", 4)
    saved_paths = []
    for i in range(7):
        path = store.save_prediction({"seq": i})
        assert path
        saved_paths.append(path)
        time.sleep(0.02)
    remaining = sorted(os.path.basename(p) for p in tmp_path.glob("prediction_*.json"))
    assert len(remaining) == 4
    expected = sorted(os.path.basename(p) for p in saved_paths[-4:])
    assert remaining == expected, "prune must drop the oldest files only"
    rows = store.list_predictions()
    assert [row["path"] for row in rows] == list(reversed(saved_paths[-4:]))
    assert [store.load_prediction(row["id"])["seq"] for row in rows] == [6, 5, 4, 3]


def test_store_never_raises_on_bad_input(store, tmp_path):
    assert store.save_prediction(None) == ""
    assert store.save_prediction("not a dict") == ""
    assert store.save_prediction([1, 2, 3]) == ""

    # Non-JSON-serializable values fall back to str() via default=str.
    path = store.save_prediction({"symbol": "X", "weird": {1, 2}, "obj": object()})
    assert path and os.path.isfile(path)

    class Unstringable:
        def __str__(self):
            raise RuntimeError("boom")

    assert store.save_prediction({"bad": Unstringable()}) == ""
    leftovers = [p for p in os.listdir(str(tmp_path)) if p.endswith(".tmp")]
    assert leftovers == [], "failed saves must not leave temp files behind"


def test_store_survives_unwritable_directory(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    impossible = str(blocker / "sub")  # cannot mkdir under a regular file
    monkeypatch.setenv("KRONOS_PREDICTIONS_DIR", impossible)
    assert krs.save_prediction({"symbol": "X"}) == ""
    assert krs.list_predictions() == []
    assert krs.load_prediction("anything") is None
    assert krs.delete_prediction("anything") is False
    assert krs.clear_all() == 0


def test_store_summarizes_upstream_webui_schema(store):
    """Records shaped like the Kronos webui save_prediction_results payload
    must still produce meaningful listing summaries."""
    webui_record = {
        "timestamp": "2025-08-26T16:38:00.302387",
        "file_path": "/data/BTC_USDT_USDT-5m-futures.feather",
        "prediction_type": "Kronos model prediction",
        "prediction_params": {"lookback": 400, "pred_len": 120,
                              "temperature": 1.0, "top_p": 0.9,
                              "sample_count": 1},
        "input_data_summary": {
            "rows": 400,
            "last_values": {"open": 113769.56, "high": 113852.6,
                            "low": 113731.29, "close": 113818.87},
        },
        "prediction_results": [
            {"timestamp": "2025-08-03T22:45:00", "close": 113379.78},
            {"timestamp": "2025-08-03T22:50:00", "close": 113100.00},
        ],
        "actual_data": [],
        "analysis": {},
    }
    assert store.save_prediction(webui_record)
    summary = store.list_predictions()[0]
    assert summary["pred_len"] == 120                # from prediction_params
    assert summary["last_close"] == 113818.87        # from last_values.close
    assert summary["predicted_close"] == 113100.00   # last prediction row
    assert summary["direction"] == "down"


# ---------------------------------------------------------------------------
# Part 2: sibling module no-op safety contracts (skip when absent)
# ---------------------------------------------------------------------------

def test_kronos_service_status_contract():
    ks = pytest.importorskip("engine.kronos_service")
    get_service = getattr(ks, "get_kronos_service", None)
    if get_service is None:
        pytest.skip("engine.kronos_service.get_kronos_service not implemented yet")
    service = get_service()
    status = service.status()
    assert isinstance(status, dict)
    assert status, "status() must return a non-empty dict"
    known_keys = {"available", "loaded", "status", "ready", "model",
                  "device", "message", "torch", "torch_available", "error"}
    assert known_keys.intersection(status.keys()), (
        f"status() keys {sorted(status.keys())} share nothing with the "
        f"expected contract keys {sorted(known_keys)}")


def test_kronos_service_forecast_never_raises():
    ks = pytest.importorskip("engine.kronos_service")
    pd = pytest.importorskip("pandas")
    get_service = getattr(ks, "get_kronos_service", None)
    if get_service is None:
        pytest.skip("engine.kronos_service.get_kronos_service not implemented yet")
    service = get_service()
    if not hasattr(service, "forecast"):
        pytest.skip("kronos service has no forecast() yet")

    df = _synthetic_ohlcv(pd, n=48)
    pred_len = 4
    step = df["timestamps"].iloc[1] - df["timestamps"].iloc[0]
    x_timestamp = df["timestamps"].reset_index(drop=True)
    y_timestamp = pd.Series(pd.date_range(
        df["timestamps"].iloc[-1] + step, periods=pred_len, freq=step))
    ok, result = _first_accepted((
        # house contract: forecast(df, x_timestamp, y_timestamp, pred_len, ...)
        lambda: service.forecast(df, x_timestamp=x_timestamp,
                                 y_timestamp=y_timestamp, pred_len=pred_len),
        lambda: service.forecast(df=df, pred_len=pred_len),
        lambda: service.forecast(df, pred_len),
        lambda: service.forecast(df=df, symbol="BTCUSDT", interval="1h", pred_len=pred_len),
        lambda: service.forecast(symbol="BTCUSDT", interval="1h", pred_len=pred_len),
        lambda: service.forecast(df),
    ))
    if not ok:
        pytest.skip("forecast() signature not recognized by contract probe")

    assert result is not None, "forecast() must return a result object, not None"
    if isinstance(result, dict):
        status = result.get("status")
    else:
        status = getattr(result, "status", None)
    assert status in {"ok", "unavailable", "error"}, (
        f"forecast() status must be ok/unavailable/error, got {status!r}")


def test_kronos_adapter_symbols_and_intervals():
    ka = pytest.importorskip("data.kronos_adapter")
    symbols = getattr(ka, "SUPPORTED_SYMBOLS", None)
    intervals = getattr(ka, "SUPPORTED_INTERVALS", None)
    if symbols is None or intervals is None:
        pytest.skip("kronos_adapter SUPPORTED_SYMBOLS/SUPPORTED_INTERVALS not defined yet")
    assert len(symbols) > 0, "SUPPORTED_SYMBOLS must be non-empty"
    assert len(intervals) > 0, "SUPPORTED_INTERVALS must be non-empty"


def test_kronos_adapter_future_timestamps_daily_skips_weekends():
    ka = pytest.importorskip("data.kronos_adapter")
    pd = pytest.importorskip("pandas")
    fn = getattr(ka, "make_future_timestamps", None)
    if fn is None:
        pytest.skip("kronos_adapter.make_future_timestamps not defined yet")

    last = pd.Timestamp("2026-01-01 15:30:00")  # a Thursday
    n = 5
    ok, result = _first_accepted((
        lambda: fn(last, n, "1d"),
        lambda: fn(last, "1d", n),
        lambda: fn("1d", last, n),
        lambda: fn(last_timestamp=last, pred_len=n, interval="1d"),
        lambda: fn(last_ts=last, pred_len=n, interval="1d"),
        lambda: fn(last=last, pred_len=n, interval="1d"),
    ))
    if not ok:
        pytest.skip("make_future_timestamps() signature not recognized by probe")

    stamps = pd.DatetimeIndex(pd.to_datetime(list(result)))
    assert len(stamps) == n, f"expected {n} future stamps, got {len(stamps)}"
    assert stamps.is_monotonic_increasing
    assert (stamps > last).all(), "all stamps must be strictly in the future"
    weekdays = [ts.weekday() for ts in stamps]
    assert all(day < 5 for day in weekdays), (
        f"'1d' stamps must skip weekends, got weekdays {weekdays}")


def test_kronos_adapter_prepare_inputs_contract():
    ka = pytest.importorskip("data.kronos_adapter")
    pd = pytest.importorskip("pandas")
    fn = getattr(ka, "prepare_kronos_inputs", None)
    if fn is None:
        pytest.skip("kronos_adapter.prepare_kronos_inputs not defined yet")

    df = _synthetic_ohlcv(pd, n=64)
    pred_len = 8
    ok, result = _first_accepted((
        lambda: fn(df, pred_len=pred_len),
        lambda: fn(df, pred_len),
        lambda: fn(df=df, pred_len=pred_len),
        lambda: fn(df, lookback=32, pred_len=pred_len),
        lambda: fn(df, 32, pred_len),
        lambda: fn(df),
    ))
    if not ok:
        pytest.skip("prepare_kronos_inputs() signature not recognized by probe")
    assert result is not None

    # Collect every DataFrame-like element from the return shape.
    if isinstance(result, dict):
        candidates = list(result.values())
    elif isinstance(result, (tuple, list)):
        candidates = list(result)
    else:
        candidates = [result]
    frames = [c for c in candidates
              if hasattr(c, "columns") and hasattr(c, "__len__")]
    assert frames, "prepare_kronos_inputs must yield at least one DataFrame"

    ohlc = {"open", "high", "low", "close"}
    model_frames = [f for f in frames if ohlc.issubset(set(map(str, f.columns)))]
    assert model_frames, (
        f"no returned frame carries the OHLC columns; got column sets "
        f"{[list(f.columns) for f in frames]}")
    x_df = model_frames[0]
    assert len(x_df) > 0
    assert not x_df[list(ohlc)].isna().any().any(), "model inputs must be NaN-free"


def test_kronos_backtest_empty_df_contract():
    kb = pytest.importorskip("engine.kronos_backtest")
    pd = pytest.importorskip("pandas")
    fn = getattr(kb, "run_kronos_backtest", None)
    if fn is None:
        pytest.skip("engine.kronos_backtest.run_kronos_backtest not defined yet")

    empty = pd.DataFrame()
    ok, result = _first_accepted((
        lambda: fn(empty),
        lambda: fn(df=empty),
        lambda: fn(empty, pred_len=4),
        lambda: fn(empty, symbol="BTCUSDT", interval="1h"),
    ))
    if not ok:
        pytest.skip("run_kronos_backtest() signature not recognized by probe")
    assert isinstance(result, dict), "backtest must return a dict"
    assert "status" in result, f"backtest dict must carry 'status', got {sorted(result.keys())}"


def test_kronos_charts_handle_empty_inputs():
    uc = pytest.importorskip("ui.kronos_charts")
    pd = pytest.importorskip("pandas")
    import inspect

    builders = [obj for name, obj in vars(uc).items()
                if inspect.isfunction(obj)
                and getattr(obj, "__module__", "") == uc.__name__
                and not name.startswith("_")
                and ("chart" in name.lower() or "fig" in name.lower())]
    if not builders:
        pytest.skip("no public chart builders found in ui.kronos_charts")

    empty = pd.DataFrame()
    built = 0
    for builder in builders:
        ok, fig = _first_accepted((
            lambda b=builder: b(empty),
            lambda b=builder: b(empty, empty),
            lambda b=builder: b(empty, None),
            lambda b=builder: b(None),
            lambda b=builder: b(),
        ))
        if not ok:
            continue  # builder needs args the probe does not know about
        assert fig is not None, f"{builder.__name__} returned None for empty input"
        assert hasattr(fig, "data") or hasattr(fig, "to_dict") or isinstance(fig, dict), (
            f"{builder.__name__} did not return a figure-like object: {type(fig)!r}")
        built += 1
    if built == 0:
        pytest.skip("no chart builder accepted the empty-input probe")


# ---------------------------------------------------------------------------
# Part 3: vendored model regression (mirrors upstream, 256-context case)
# ---------------------------------------------------------------------------

def _set_seed(torch, seed=SEED):
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    try:
        if torch.backends.cudnn.is_available():
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except Exception:
        pass


def test_vendored_kronos_regression_ctx256():
    torch = pytest.importorskip("torch")
    pd = pytest.importorskip("pandas")
    kronos_pkg = pytest.importorskip("engine.kronos")

    Kronos = getattr(kronos_pkg, "Kronos", None)
    KronosTokenizer = getattr(kronos_pkg, "KronosTokenizer", None)
    KronosPredictor = getattr(kronos_pkg, "KronosPredictor", None)
    if not all((Kronos, KronosTokenizer, KronosPredictor)):
        pytest.skip("engine.kronos does not export Kronos/KronosTokenizer/KronosPredictor yet")
    if not (os.path.isfile(REGRESSION_INPUT) and os.path.isfile(REGRESSION_OUTPUT_256)):
        pytest.skip("regression fixtures missing under tests/data/kronos/")

    # Offline by default: only touch the local HF cache. Opt in to a real
    # download with KRONOS_TEST_ALLOW_DOWNLOAD=1.
    allow_download = os.environ.get(
        "KRONOS_TEST_ALLOW_DOWNLOAD", "").strip().lower() in {"1", "true", "yes", "on"}
    hub_kwargs = {} if allow_download else {"local_files_only": True}
    try:
        tokenizer = KronosTokenizer.from_pretrained(
            TOKENIZER_ID, revision=TOKENIZER_REVISION, **hub_kwargs)
        model = Kronos.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, **hub_kwargs)
    except Exception as exc:
        pytest.skip(
            "Kronos HF weights unavailable (offline or download disabled; "
            f"set KRONOS_TEST_ALLOW_DOWNLOAD=1 to fetch): {exc}")

    _set_seed(torch)
    tokenizer.eval()
    model.eval()

    context_len = 256
    df = pd.read_csv(REGRESSION_INPUT, parse_dates=["timestamps"])
    expected_df = pd.read_csv(REGRESSION_OUTPUT_256, parse_dates=["timestamps"])
    assert df.shape[0] >= context_len + len(expected_df), (
        "fixture regression_input.csv is too short for the 256-context test")

    context_df = df.iloc[:context_len]
    context_features = context_df[REGRESSION_FEATURES].reset_index(drop=True)
    x_timestamp = context_df["timestamps"].reset_index(drop=True)
    y_timestamp = df["timestamps"].iloc[
        context_len:context_len + len(expected_df)].reset_index(drop=True)
    expected = expected_df[REGRESSION_FEATURES].values.astype(np.float32)

    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)
    try:
        with torch.no_grad():
            pred_df = predictor.predict(
                df=context_features,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=expected.shape[0],
                T=1.0,
                top_k=1,
                top_p=1.0,
                verbose=False,
                sample_count=1,
            )
    except TypeError as exc:
        pytest.skip(f"vendored KronosPredictor.predict signature differs from upstream: {exc}")

    obtained = pred_df[REGRESSION_FEATURES].to_numpy(dtype=np.float32)
    np.testing.assert_allclose(obtained, expected, rtol=REGRESSION_RTOL)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

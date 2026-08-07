"""
ZERO Kronos Forecast Service
============================

Crash-proof service wrapper around the vendored Kronos K-line foundation
model (``engine/kronos`` — MIT, github.com/shiyu-coder/Kronos) for ZERO's
prediction stack.  Unlike the single-bar envelope leg in
``engine/tsfm_predictor.py``, this service exposes the FULL Kronos surface:
multi-bar OHLCV(A) forecasts, Monte-Carlo close paths with empirical
P10/P50/P90 bands, batch prediction, and the Kronos-webui-style volatility
amplification post-processing step.

No-op safety contract (ZERO house rules)
----------------------------------------
* Core deps are only numpy / pandas.  torch and the vendored
  ``engine.kronos`` package are OPTIONAL and imported lazily inside
  ``load()`` — this module always imports cleanly with neither installed.
* Nothing is downloaded at import time.  Hugging Face weights are fetched
  on the first ``load()`` / ``forecast()`` call, fully wrapped; a hard load
  failure is latched so a broken backend is not retried every call.
* No public method ever raises: failures degrade to results with
  ``status in ('unavailable', 'error')`` and an ``error`` message.

Environment overrides (all optional)
------------------------------------
KRONOS_MODEL_ID      Hugging Face model id     (NeoQuasar/Kronos-small)
KRONOS_TOKENIZER_ID  Hugging Face tokenizer id (NeoQuasar/Kronos-Tokenizer-base)
KRONOS_DEVICE        torch device string; 'auto' = cuda if available else cpu
KRONOS_MAX_CONTEXT   max context bars fed to the model (512)
HF_TOKEN / HUGGING_FACE_HUB_TOKEN
                     Optional Hugging Face Hub token (also config.HF_TOKEN).
                     Public NeoQuasar models work without it; token raises
                     anonymous rate limits.  When the local HF cache already
                     has the weights, load uses local_files_only (no Hub hit).
TRANSFORMERS_VERBOSITY
                     Forced to 'error' during load for a quiet Streamlit UI.
HF_HUB_OFFLINE       If already set by the user, respected; otherwise we
                     prefer local_files_only when cache is warm.

Sampling note
-------------
Upstream ``KronosPredictor.predict`` AVERAGES its ``sample_count`` paths
internally, so it cannot return per-path forecasts.  When
``sample_count >= 4`` this service instead draws that many INDEPENDENT
paths — one ``predict_batch`` call with the series repeated ``sample_count``
times at ``sample_count=1`` (single batched pass), falling back to
sequential ``predict`` calls — then reports the element-wise mean as
``pred_df`` plus per-step empirical close bands (the same
sampled-paths-to-percentiles approach as ``tsfm_predictor._forecast_kronos``).

Usage (engine.* callers)
------------------------
    from engine.kronos_service import get_kronos_service

    svc = get_kronos_service()      # cheap singleton; no weights loaded
    print(svc.status())             # dependency / load state, never loads
    res = svc.forecast(df, x_timestamp, y_timestamp, pred_len=24,
                       T=1.0, top_p=0.9, sample_count=8, vol_amp=1.2)
    if res.status == 'ok':
        print(res.pred_df.tail())   # open/high/low/close/volume/amount
        print(res.close_p10, res.close_p50, res.close_p90)
"""
from __future__ import annotations

import importlib.util
import logging
import os
import threading
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd


# ── Env-overridable constants ────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


KRONOS_MODEL_ID = os.environ.get("KRONOS_MODEL_ID", "NeoQuasar/Kronos-small")
KRONOS_TOKENIZER_ID = os.environ.get("KRONOS_TOKENIZER_ID",
                                     "NeoQuasar/Kronos-Tokenizer-base")
KRONOS_DEVICE = os.environ.get("KRONOS_DEVICE", "auto").strip() or "auto"
KRONOS_MAX_CONTEXT = _env_int("KRONOS_MAX_CONTEXT", 512)

# Short UI caption — public models need no token; rate limits apply anonymously.
HF_HUB_AUTH_CAPTION = (
    "Public NeoQuasar/Kronos weights load without a Hugging Face token; "
    "set HF_TOKEN (or HUGGING_FACE_HUB_TOKEN) to raise rate limits. "
    "Warm HF cache loads offline - Streamlit will not re-hit the Hub."
)

_PRICE_COLS = ("open", "high", "low", "close")
_OPT_COLS = ("volume", "amount")


class _HfUnauthWarningFilter(logging.Filter):
    """Drop the noisy 'unauthenticated requests to the HF Hub' UserWarning
    when no token is configured — public models still work; we surface the
    rate-limit note via HF_HUB_AUTH_CAPTION / status() instead."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "unauthenticated requests to the HF Hub" in msg:
            return False
        if "Please set a HF_TOKEN" in msg:
            return False
        return True


def hf_hub_auth_caption() -> str:
    """Stable one-liner for Streamlit captions (token optional, cache preferred)."""
    return HF_HUB_AUTH_CAPTION


def _resolve_hf_token() -> str | None:
    """Optional Hub token from env or config.HF_TOKEN (GEMINI_API_KEY style).

    Never required — returns None when unset so anonymous public downloads
    still work (subject to Hub rate limits).
    """
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        raw = os.environ.get(key, "")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    try:
        from config import HF_TOKEN as cfg_token  # type: ignore
        if isinstance(cfg_token, str) and cfg_token.strip():
            return cfg_token.strip()
    except Exception:
        pass
    return None


def _hub_repo_cached(repo_id: str) -> bool:
    """True when the local Hugging Face cache already has ``config.json`` for
    ``repo_id`` — enough to prefer ``local_files_only`` and skip Hub traffic."""
    try:
        from huggingface_hub import try_to_load_from_cache
        try:
            from huggingface_hub import _CACHED_NO_EXIST
        except ImportError:
            _CACHED_NO_EXIST = object()  # type: ignore
        path = try_to_load_from_cache(repo_id, "config.json")
        if path is None or path is _CACHED_NO_EXIST:
            return False
        return bool(path) and os.path.isfile(str(path))
    except Exception:
        return False


def _quiet_hub_logging() -> None:
    """Reduce Hub chatter during Kronos weight load.

    Kronos uses ``huggingface_hub`` + safetensors + torch — it does **not**
    need ``transformers``.  Never ``import transformers`` here: that pulls
    ``transformers.models.*`` vision stacks into ``sys.modules`` and makes
    Streamlit's file watcher spam torchvision errors on every script rerun.
    If another subsystem already imported transformers, quiet its logger only.
    """
    import sys

    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    try:
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
        logging.getLogger("huggingface_hub.utils").setLevel(logging.ERROR)
        logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)
    except Exception:
        pass

    # Quiet transformers ONLY if already imported — do not import it to quiet it.
    if "transformers" in sys.modules:
        try:
            tf = sys.modules["transformers"]
            set_err = getattr(getattr(tf, "logging", None), "set_verbosity_error", None)
            if callable(set_err):
                set_err()
        except Exception:
            pass
        try:
            logging.getLogger("transformers").setLevel(logging.ERROR)
        except Exception:
            pass

    # Downgrade / suppress the unauthenticated-Hub warning in UI logs.
    flt = _HfUnauthWarningFilter()
    for name in ("huggingface_hub", "huggingface_hub.utils",
                 "huggingface_hub.utils._http", "transformers"):
        logging.getLogger(name).addFilter(flt)
    # warnings.warn path used by some hub versions
    try:
        import warnings
        warnings.filterwarnings(
            "ignore",
            message=r".*unauthenticated requests to the HF Hub.*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r".*Please set a HF_TOKEN.*",
            category=UserWarning,
        )
    except Exception:
        pass


def _load_pretrained(cls, repo_id: str, **kwargs):
    """``from_pretrained`` with local-cache-first, online fallback.

    Never imports transformers — Kronos Mixins live on huggingface_hub.
    """
    # Prefer local snapshot when available / already requested.
    try:
        kw_local = dict(kwargs)
        kw_local["local_files_only"] = True
        return cls.from_pretrained(repo_id, **kw_local)
    except Exception:
        pass
    kw_net = dict(kwargs)
    kw_net.pop("local_files_only", None)
    return cls.from_pretrained(repo_id, **kw_net)


def _from_pretrained_kwargs(repo_id: str, token: str | None) -> dict:
    """Build kwargs for ``*.from_pretrained``: optional token + local cache prefer."""
    kw: dict = {}
    if token:
        kw["token"] = token
    # Prefer offline / local when cache is warm (or user already set HF_HUB_OFFLINE).
    offline = (os.environ.get("HF_HUB_OFFLINE", "") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if offline or _hub_repo_cached(repo_id):
        kw["local_files_only"] = True
    return kw


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class KronosForecastResult:
    """Outcome of one Kronos forecast.  Fields are None when not produced.

    pred_df      : DataFrame open/high/low/close/volume/amount indexed by the
                   future timestamps (mean across paths when sample_count>=4).
    sample_paths : list of per-path close ndarrays (len pred_len) or None.
    close_p10/50/90 : per-step empirical close bands (ndarray, len pred_len)
                   when sample_count >= 4, else None.
    status       : 'ok' | 'unavailable' | 'error'.
    """

    pred_df: pd.DataFrame | None = None
    sample_paths: list | None = None
    close_p10: np.ndarray | None = None
    close_p50: np.ndarray | None = None
    close_p90: np.ndarray | None = None
    status: str = "ok"
    error: str = ""
    elapsed_s: float = 0.0
    model_id: str = ""
    device: str = ""


# ── Service ──────────────────────────────────────────────────────────────────

class KronosService:
    """Lazy-loading Kronos predictor service.

    Construction is free: no imports of torch / engine.kronos, no downloads.
    ``load()`` (auto-invoked by the forecast methods) performs the lazy heavy
    imports and pulls the Hugging Face weights; every failure is captured and
    surfaced through ``status()`` — no public method ever raises.
    """

    def __init__(self, model_id: str | None = None, tokenizer_id: str | None = None,
                 device: str | None = None, max_context: int | None = None):
        self.model_id = (model_id or KRONOS_MODEL_ID).strip()
        self.tokenizer_id = (tokenizer_id or KRONOS_TOKENIZER_ID).strip()
        self.device = (device or KRONOS_DEVICE).strip() or "auto"
        try:
            self.max_context = max(1, int(max_context if max_context is not None
                                          else KRONOS_MAX_CONTEXT))
        except (TypeError, ValueError):
            self.max_context = 512

        self._lock = threading.Lock()
        self._predictor = None            # loaded KronosPredictor instance
        self._resolved_device: str | None = None
        self._load_failed = False         # latched hard failure (download/init)
        self._deps_missing = False        # soft: torch / package absent
        self._load_error = ""

    # ── Cheap dependency probes (find_spec only — never import torch,
    #    never execute the vendored package, never touch the network) ─────

    @staticmethod
    def _probe_torch() -> bool:
        try:
            return importlib.util.find_spec("torch") is not None
        except Exception:
            return False

    @staticmethod
    def _probe_package() -> bool:
        try:
            return importlib.util.find_spec("engine.kronos") is not None
        except Exception:
            return False

    @staticmethod
    def _probe_torchvision() -> bool:
        """find_spec only — never import torchvision (or transformers vision)."""
        try:
            return importlib.util.find_spec("torchvision") is not None
        except Exception:
            return False

    # ── Status / availability ────────────────────────────────────────────

    def status(self) -> dict:
        """Cheap state snapshot — NEVER loads the model or hits the network."""
        try:
            token = _resolve_hf_token()
            return {
                "torch_available": self._probe_torch(),
                "package_available": self._probe_package(),
                "torchvision_available": self._probe_torchvision(),
                "model_loaded": self._predictor is not None,
                "device": self._resolved_device or self.device,
                "model_id": self.model_id,
                "tokenizer_id": self.tokenizer_id,
                "error": self._load_error,
                "hf_token_set": bool(token),
                "hf_cache_warm": (
                    _hub_repo_cached(self.model_id)
                    and _hub_repo_cached(self.tokenizer_id)
                ),
                "hf_auth_caption": HF_HUB_AUTH_CAPTION,
            }
        except Exception as exc:  # absolute no-raise guarantee
            return {
                "torch_available": False, "package_available": False,
                "torchvision_available": False,
                "model_loaded": False, "device": self.device,
                "model_id": self.model_id, "tokenizer_id": self.tokenizer_id,
                "error": str(exc),
                "hf_token_set": False, "hf_cache_warm": False,
                "hf_auth_caption": HF_HUB_AUTH_CAPTION,
            }

    def available(self) -> bool:
        """True when a forecast could plausibly run (deps present or model
        already loaded).  Cheap probe only — never loads weights."""
        try:
            if self._predictor is not None:
                return True
            if self._load_failed:
                return False
            return self._probe_torch() and self._probe_package()
        except Exception:
            return False

    # ── Lazy loading ─────────────────────────────────────────────────────

    def load(self) -> bool:
        """Lazily import torch + engine.kronos and pull the HF weights.
        Thread-safe, idempotent, never raises; False on any failure with the
        reason recorded in ``status()['error']``."""
        try:
            with self._lock:
                return self._load_locked()
        except Exception as exc:
            self._load_error = str(exc)
            return False

    def _load_locked(self) -> bool:
        if self._predictor is not None:
            return True
        if self._load_failed:
            return False  # latched: don't re-download a broken backend

        # Soft dependency gates — re-probed each call (cheap, not latched).
        self._deps_missing = False
        if not self._probe_torch():
            self._deps_missing = True
            self._load_error = "torch not installed - Kronos backend disabled"
            return False
        if not self._probe_package():
            self._deps_missing = True
            self._load_error = "vendored engine.kronos package not available"
            return False

        try:
            _quiet_hub_logging()
            import torch  # lazy heavy import
            from engine.kronos import (  # lazy vendored import
                Kronos, KronosPredictor, KronosTokenizer,
            )

            token = _resolve_hf_token()
            tok_kw = _from_pretrained_kwargs(self.tokenizer_id, token)
            model_kw = _from_pretrained_kwargs(self.model_id, token)

            tokenizer = _load_pretrained(
                KronosTokenizer, self.tokenizer_id, **tok_kw)
            model = _load_pretrained(Kronos, self.model_id, **model_kw)

            device = self.device
            if device.lower() in ("", "auto"):
                device = "cuda" if torch.cuda.is_available() else "cpu"

            self._predictor = KronosPredictor(model, tokenizer, device=device,
                                              max_context=self.max_context)
            self._resolved_device = device
            self._load_error = ""
            return True
        except Exception as exc:  # import/download/init failure → latch
            self._load_failed = True
            self._load_error = f"kronos load failed: {exc}"
            return False

    # ── Public forecast API ──────────────────────────────────────────────

    def forecast(self, df, x_timestamp, y_timestamp, pred_len,
                 T: float = 1.0, top_p: float = 0.9, sample_count: int = 1,
                 vol_amp: float = 1.0) -> KronosForecastResult:
        """Multi-bar OHLCV(A) forecast.  Auto-loads on first call; NEVER raises.

        df           : DataFrame with open/high/low/close (+optional volume /
                       amount); extra columns ignored, case-insensitive.
        x_timestamp  : per-row historical timestamps (Series/Index/array).
        y_timestamp  : future timestamps, at least ``pred_len`` long.
        T / top_p    : sampling temperature / nucleus probability.
        sample_count : 1-3 → one predict call (paths averaged upstream);
                       >= 4 → that many independent paths + empirical
                       close_p10/p50/p90 bands and sample_paths.
        vol_amp      : != 1.0 scales each predicted bar's O/H/L deviation
                       around its close (Kronos-webui volatility amplification).
        """
        t0 = time.time()
        try:
            pred_len = self._i(pred_len, 1)
            T = self._f(T, 1.0)
            top_p = self._f(top_p, 0.9)
            sample_count = self._i(sample_count, 1)
            vol_amp = self._f(vol_amp, 1.0)

            # Validate inputs BEFORE load() so malformed calls never trigger
            # heavy imports or a Hugging Face download.
            kdf = self._prep_df(df)
            if kdf is None:
                return self._finish(self._result(
                    "error", "input df missing open/high/low/close data"), t0)
            x_ts = self._ts_series(x_timestamp)
            y_ts = self._ts_series(y_timestamp)
            if x_ts is None or y_ts is None:
                return self._finish(self._result(
                    "error", "x_timestamp/y_timestamp not parseable as datetimes"), t0)
            if len(x_ts) != len(kdf):
                return self._finish(self._result(
                    "error", f"x_timestamp length {len(x_ts)} != df rows {len(kdf)}"), t0)
            if len(y_ts) < pred_len:
                return self._finish(self._result(
                    "error", f"y_timestamp length {len(y_ts)} < pred_len {pred_len}"), t0)
            y_ts = y_ts.iloc[:pred_len].reset_index(drop=True)
            kdf, x_ts = self._trim_context(kdf, x_ts)

            if not self.load():
                status = "unavailable" if self._deps_missing else "error"
                return self._finish(self._result(status, self._load_error), t0)

            if sample_count >= 4:
                paths = self._sample_paths(kdf, x_ts, y_ts, pred_len,
                                           T, top_p, sample_count)
                cols = list(paths[0].columns)
                stacked = np.stack(
                    [p.to_numpy(dtype=float) for p in paths], axis=0)
                pred_df = pd.DataFrame(stacked.mean(axis=0), columns=cols,
                                       index=paths[0].index)
                ci = cols.index("close") if "close" in cols else len(cols) - 1
                close_mat = stacked[:, :, ci]  # (n_paths, pred_len)
                sample_paths = [close_mat[i].copy()
                                for i in range(close_mat.shape[0])]
                close_p10 = np.percentile(close_mat, 10, axis=0)
                close_p50 = np.percentile(close_mat, 50, axis=0)
                close_p90 = np.percentile(close_mat, 90, axis=0)
            else:
                pred_df = self._predictor.predict(
                    df=kdf, x_timestamp=x_ts, y_timestamp=y_ts,
                    pred_len=pred_len, T=T, top_p=top_p,
                    sample_count=sample_count, verbose=False)
                sample_paths = None
                close_p10 = close_p50 = close_p90 = None

            if vol_amp != 1.0:
                pred_df = self._apply_vol_amp(pred_df, vol_amp)

            return self._finish(self._result(
                "ok", pred_df=pred_df, sample_paths=sample_paths,
                close_p10=close_p10, close_p50=close_p50, close_p90=close_p90), t0)
        except Exception as exc:  # absolute no-raise guarantee
            return self._finish(self._result("error", str(exc)), t0)

    def forecast_batch(self, df_list, x_ts_list, y_ts_list, pred_len,
                       T: float = 1.0, top_p: float = 0.9, sample_count: int = 1,
                       vol_amp: float = 1.0) -> list:
        """Forecast several series; returns one KronosForecastResult per input.

        Uses ``predict_batch`` (single batched pass) when available and no
        quantile bands are requested (sample_count < 4); otherwise falls back
        to sequential ``forecast()`` calls.  NEVER raises.
        """
        t0 = time.time()
        try:
            n = len(df_list)
        except Exception:
            return [self._finish(self._result(
                "error", "df_list is not a sized sequence"), t0)]
        try:
            if not (self._sized(x_ts_list) == self._sized(y_ts_list) == n):
                return [self._finish(self._result(
                    "error", "df_list/x_ts_list/y_ts_list length mismatch"), t0)
                    for _ in range(max(1, n))]
            if n == 0:
                return []

            pred_len = self._i(pred_len, 1)
            T = self._f(T, 1.0)
            top_p = self._f(top_p, 0.9)
            sample_count = self._i(sample_count, 1)
            vol_amp = self._f(vol_amp, 1.0)

            if not self.load():
                status = "unavailable" if self._deps_missing else "error"
                return [self._finish(self._result(status, self._load_error), t0)
                        for _ in range(n)]

            # Batched fast path: no per-path bands wanted and API available.
            if sample_count < 4 and hasattr(self._predictor, "predict_batch"):
                results = self._try_batch(df_list, x_ts_list, y_ts_list,
                                          pred_len, T, top_p, sample_count,
                                          vol_amp, t0)
                if results is not None:
                    return results

            # Sequential fallback (also the sample_count >= 4 quantile path).
            return [self.forecast(df_list[i], x_ts_list[i], y_ts_list[i],
                                  pred_len, T=T, top_p=top_p,
                                  sample_count=sample_count, vol_amp=vol_amp)
                    for i in range(n)]
        except Exception as exc:  # absolute no-raise guarantee
            return [self._finish(self._result("error", str(exc)), t0)
                    for _ in range(max(1, n))]

    # ── Internals ────────────────────────────────────────────────────────

    def _try_batch(self, df_list, x_ts_list, y_ts_list, pred_len,
                   T, top_p, sample_count, vol_amp, t0):
        """One predict_batch pass; None → caller uses the sequential path."""
        try:
            kdfs, xss, yss = [], [], []
            for i in range(len(df_list)):
                kdf = self._prep_df(df_list[i])
                x_ts = self._ts_series(x_ts_list[i])
                y_ts = self._ts_series(y_ts_list[i])
                if (kdf is None or x_ts is None or y_ts is None
                        or len(x_ts) != len(kdf) or len(y_ts) < pred_len):
                    return None  # let forecast() report the precise error
                kdf, x_ts = self._trim_context(kdf, x_ts)
                kdfs.append(kdf)
                xss.append(x_ts)
                yss.append(y_ts.iloc[:pred_len].reset_index(drop=True))

            dfs = self._predictor.predict_batch(
                kdfs, xss, yss, pred_len=pred_len, T=T, top_p=top_p,
                sample_count=sample_count, verbose=False)
            if not isinstance(dfs, (list, tuple)) or len(dfs) != len(kdfs):
                return None

            results = []
            for pdf in dfs:
                if vol_amp != 1.0:
                    pdf = self._apply_vol_amp(pdf, vol_amp)
                results.append(self._finish(self._result("ok", pred_df=pdf), t0))
            return results
        except Exception:
            return None  # e.g. unequal lookback lengths → sequential fallback

    def _sample_paths(self, kdf, x_ts, y_ts, pred_len, T, top_p, n: int) -> list:
        """n INDEPENDENT forecast paths (upstream predict() averages its
        sample_count internally, so paths must be drawn separately).
        Prefers one batched pass — the series repeated n times at
        sample_count=1 — falling back to n sequential predict calls."""
        predictor = self._predictor
        try:
            if hasattr(predictor, "predict_batch"):
                dfs = predictor.predict_batch(
                    [kdf] * n, [x_ts] * n, [y_ts] * n, pred_len=pred_len,
                    T=T, top_p=top_p, sample_count=1, verbose=False)
                if isinstance(dfs, (list, tuple)) and len(dfs) == n:
                    return list(dfs)
        except Exception:
            pass  # fall through to sequential sampling
        return [predictor.predict(df=kdf, x_timestamp=x_ts, y_timestamp=y_ts,
                                  pred_len=pred_len, T=T, top_p=top_p,
                                  sample_count=1, verbose=False)
                for _ in range(n)]

    def _trim_context(self, kdf: pd.DataFrame, x_ts: pd.Series):
        """Keep the most recent max_context bars (predictor truncates too —
        trimming here avoids tokenizing an oversized sequence)."""
        if len(kdf) > self.max_context:
            kdf = kdf.iloc[-self.max_context:].reset_index(drop=True)
            x_ts = x_ts.iloc[-self.max_context:].reset_index(drop=True)
        return kdf, x_ts

    @staticmethod
    def _apply_vol_amp(pred_df: pd.DataFrame, vol_amp: float) -> pd.DataFrame:
        """Kronos-webui-style volatility amplification: scale each predicted
        bar's open/high/low deviation around its close by ``vol_amp`` (close,
        volume and amount unchanged), then re-enforce OHLC consistency."""
        try:
            out = pred_df.copy()
            cols = {str(c).lower(): c for c in out.columns}
            if "close" not in cols:
                return pred_df
            close = out[cols["close"]].astype(float)
            for name in ("open", "high", "low"):
                if name in cols:
                    c = cols[name]
                    out[c] = close + (out[c].astype(float) - close) * float(vol_amp)
            present = [cols[p] for p in _PRICE_COLS if p in cols]
            if "high" in cols:
                out[cols["high"]] = out[present].max(axis=1)
            if "low" in cols:
                out[cols["low"]] = out[present].min(axis=1)
            return out
        except Exception:
            return pred_df  # amplification is cosmetic — never fail the forecast

    # ── Input coercion helpers ───────────────────────────────────────────

    @staticmethod
    def _prep_df(df) -> pd.DataFrame | None:
        """Lowercase-OHLC(+volume/amount) numeric frame, or None if unusable."""
        try:
            if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                return None
            out = df.copy()
            if isinstance(out.columns, pd.MultiIndex):
                out.columns = out.columns.get_level_values(0)
            out.columns = [str(c).strip().lower() for c in out.columns]
            if any(c not in out.columns for c in _PRICE_COLS):
                return None
            cols = list(_PRICE_COLS) + [c for c in _OPT_COLS if c in out.columns]
            out = out[cols]
            for c in cols:
                out[c] = pd.to_numeric(out[c], errors="coerce")
            return out.reset_index(drop=True)
        except Exception:
            return None

    @staticmethod
    def _ts_series(ts) -> pd.Series | None:
        """Coerce to a clean datetime64 Series (Kronos needs the .dt accessor,
        so a DatetimeIndex must become a Series), or None if unusable."""
        try:
            if ts is None:
                return None
            if isinstance(ts, pd.DatetimeIndex):
                s = pd.Series(ts)
            elif isinstance(ts, pd.Series):
                s = pd.to_datetime(ts)
            else:
                s = pd.Series(pd.to_datetime(list(ts)))
            s = s.reset_index(drop=True)
            if len(s) == 0 or s.isna().any():
                return None
            return s
        except Exception:
            return None

    @staticmethod
    def _sized(x) -> int:
        try:
            return len(x)
        except Exception:
            return -1

    @staticmethod
    def _f(value, default: float) -> float:
        try:
            v = float(value)
            return v if np.isfinite(v) else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _i(value, default: int, minimum: int = 1) -> int:
        try:
            return max(minimum, int(value))
        except (TypeError, ValueError):
            return default

    # ── Result helpers ───────────────────────────────────────────────────

    def _result(self, status: str, error: str = "", **kw) -> KronosForecastResult:
        return KronosForecastResult(
            status=status, error=str(error or ""),
            model_id=self.model_id,
            device=self._resolved_device or self.device, **kw)

    @staticmethod
    def _finish(res: KronosForecastResult, t0: float) -> KronosForecastResult:
        try:
            res.elapsed_s = round(time.time() - t0, 3)
        except Exception:
            pass
        return res


# ── Module singleton accessor ────────────────────────────────────────────────

_SERVICE_LOCK = threading.Lock()
_SERVICE: KronosService | None = None


def get_kronos_service() -> KronosService:
    """Lazy, thread-safe module singleton.  Construction is free (no imports
    of torch / engine.kronos, no downloads) — heavy work only happens inside
    ``load()`` / the forecast methods."""
    global _SERVICE
    if _SERVICE is None:
        with _SERVICE_LOCK:
            if _SERVICE is None:
                _SERVICE = KronosService()
    return _SERVICE


if __name__ == "__main__":
    # Self-test: safe to run with zero optional deps installed.
    print("ZERO Kronos Service")
    svc = get_kronos_service()
    st = svc.status()
    print(f"  status:    {st}")
    print(f"  available: {svc.available()}")
    print(f"  hf_token_set: {st.get('hf_token_set')}  "
          f"hf_cache_warm: {st.get('hf_cache_warm')}")
    print(f"  caption:   {hf_hub_auth_caption()}")

    _rng = np.random.default_rng(7)
    _n = 64
    _close = 100.0 * np.cumprod(1.0 + _rng.normal(0.0, 0.01, _n))
    _demo = pd.DataFrame({
        "open": _close * (1.0 + _rng.normal(0.0, 0.002, _n)),
        "high": _close * (1.0 + abs(_rng.normal(0.0, 0.004, _n))),
        "low": _close * (1.0 - abs(_rng.normal(0.0, 0.004, _n))),
        "close": _close,
        "volume": abs(_rng.normal(1e6, 2e5, _n)),
    })
    _x_ts = pd.date_range("2026-01-01", periods=_n, freq="D")
    _y_ts = pd.date_range(_x_ts[-1] + pd.Timedelta(days=1), periods=4, freq="D")
    _res = svc.forecast(_demo, _x_ts, _y_ts, pred_len=4, sample_count=1)
    print(f"  forecast:  status={_res.status!r} error={_res.error!r} "
          f"elapsed={_res.elapsed_s}s device={_res.device!r}")
    if _res.pred_df is not None:
        print(_res.pred_df)

"""Kronos CSV finetuning pipeline for the ZERO trading terminal.

Finetunes the Kronos financial foundation model (tokenizer + autoregressive
predictor) on your own CSV K-line data — e.g. NIFTY50 daily candles — so the
checkpoints can be used by the vendored ``engine.kronos`` package
(``Kronos``, ``KronosTokenizer``, ``KronosPredictor``).

Ported from the upstream Kronos project's ``finetune_csv`` pipeline,
https://github.com/shiyu-coder/Kronos — MIT License, credit to the original
Kronos authors. (Upstream also ships a qlib-based ``finetune`` pipeline;
that one is reference-only and intentionally not ported.)

Modules
-------
``config_loader``
    YAML config -> :class:`CustomFinetuneConfig` with validation and ZERO
    defaults (outputs under ``D:\\ZERO_FRESH\\db\\kronos_finetune\\``).
``dataset``
    ``CustomKlineDataset`` over CSVs with columns
    ``['timestamps','open','high','low','close','volume','amount']``,
    chronological train/val split and upstream-faithful windowing and
    normalisation, plus ``create_dataloaders``.
``finetune_tokenizer``
    Stage 1 — tokenizer finetuning loop (single device, tqdm, best-val
    checkpointing).
``finetune_model``
    Stage 2 — Kronos predictor finetuning loop (loads the stage-1
    tokenizer).
``run_sequential``
    Orchestrator running both stages from one config.

Quickstart (from ``D:\\ZERO_FRESH``)::

    python -m engine.kronos_finetune.run_sequential --config engine/kronos_finetune/configs/example_nifty_daily.yaml

This package imports without torch/pandas installed; heavy dependencies are
only required when training actually runs.
"""

import importlib

__all__ = [
    "ConfigLoader",
    "CustomFinetuneConfig",
    "FinetuneConfig",
    "CustomKlineDataset",
    "create_dataloaders",
    "train_tokenizer",
    "train_model",
    "SequentialTrainer",
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_PRETRAINED_TOKENIZER",
    "DEFAULT_PRETRAINED_PREDICTOR",
]

#: Lazy export table: attribute name -> submodule that defines it.
_LAZY_EXPORTS = {
    "ConfigLoader": ".config_loader",
    "CustomFinetuneConfig": ".config_loader",
    "FinetuneConfig": ".config_loader",
    "DEFAULT_OUTPUT_ROOT": ".config_loader",
    "DEFAULT_PRETRAINED_TOKENIZER": ".config_loader",
    "DEFAULT_PRETRAINED_PREDICTOR": ".config_loader",
    "CustomKlineDataset": ".dataset",
    "create_dataloaders": ".dataset",
    "train_tokenizer": ".finetune_tokenizer",
    "train_model": ".finetune_model",
    "SequentialTrainer": ".run_sequential",
}


def __getattr__(name):
    """PEP 562 lazy attribute access.

    Submodules are only imported when one of their exports is first touched,
    and any failure (e.g. a missing optional dependency) surfaces as an
    AttributeError at *use* time — ``import engine.kronos_finetune`` itself
    can therefore never fail.
    """
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        module = importlib.import_module(target, __name__)
    except Exception as exc:
        raise AttributeError(
            f"{__name__}.{name} is unavailable because importing "
            f"{__name__}{target} failed: {exc}"
        ) from exc
    return getattr(module, name)


def __dir__():
    return sorted(set(list(globals().keys()) + list(_LAZY_EXPORTS.keys())))

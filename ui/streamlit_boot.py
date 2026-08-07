"""
Early Streamlit boot guards for ZERO.

Import this module FIRST in app.py (before local imports that may pull
Hugging Face / torch stacks). It:

1. Sets safe default env vars (tokenizers, HF hub).
2. Patches streamlit.watcher.local_sources_watcher.get_module_paths so
   Streamlit never walks transformers / torch lazy modules — that walk
   triggers transformers.__getattr__ → vision imports → torchvision spam
   (and is wasteful even when torchvision is installed).

Safe with or without torchvision / transformers / torch installed.
Kronos / TSFM remain lazy-loaded on user action (button / forecast).
"""
from __future__ import annotations

import os
import sys
from types import ModuleType
from typing import Callable, Set

# ── Env defaults (idempotent; never override an explicit user setting) ───────
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Reduce HF / transformers side effects during import probes
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

# Package roots whose modules must not be path-probed by Streamlit.
# Matching is by top-level name (e.g. transformers.models.vit → transformers).
_WATCH_SKIP_ROOTS = frozenset(
    {
        "transformers",
        "torch",
        "torchvision",
        "torchaudio",
        "torchgen",
        "functorch",
        "huggingface_hub",
        "tokenizers",
        "safetensors",
        "chronos",
        "einops",
        "accelerate",
        "peft",
        "timm",
        "datasets",
        "diffusers",
    }
)

_patched = False


def _module_root(module: ModuleType) -> str:
    name = getattr(module, "__name__", "") or ""
    return name.split(".", 1)[0]


def _safe_file_only(module: ModuleType) -> Set[str]:
    """Return {__file__} without triggering custom __getattr__ chains."""
    paths: Set[str] = set()
    try:
        # object.__getattribute__ bypasses module-level __getattr__
        f = object.__getattribute__(module, "__file__")
        if isinstance(f, str) and (os.path.isfile(f) or os.path.isdir(f)):
            paths.add(os.path.realpath(f))
    except Exception:
        pass
    return paths


def apply_watcher_guards() -> bool:
    """
    Patch Streamlit's get_module_paths to skip heavy / lazy HF stacks.

    Returns True if the patch was applied (or already applied).
    Never raises — Streamlit must still boot if watcher internals change.
    """
    global _patched
    if _patched:
        return True

    try:
        from streamlit.watcher import local_sources_watcher as _lsw
    except Exception:
        return False

    orig: Callable[[ModuleType], Set[str]] = _lsw.get_module_paths

    def get_module_paths_guarded(module: ModuleType) -> Set[str]:
        root = _module_root(module)
        if root in _WATCH_SKIP_ROOTS:
            # Do not call upstream extractors (hasattr / __path__ probes can
            # invoke transformers.__getattr__ → torchvision ImportError spam).
            return _safe_file_only(module)
        try:
            return orig(module)
        except Exception:
            # Tolerate mid-install / partial packages (e.g. torchvision landing).
            return _safe_file_only(module)

    _lsw.get_module_paths = get_module_paths_guarded  # type: ignore[attr-defined]
    _patched = True
    return True


# Apply immediately on import so the first successful script run is covered
# before LocalSourcesWatcher.update_watched_modules() scans sys.modules.
apply_watcher_guards()

# Optional: if someone imports this outside Streamlit, stay silent.
if "streamlit" not in sys.modules:
    pass

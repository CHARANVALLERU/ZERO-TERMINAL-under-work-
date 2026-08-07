"""
Runtime dependency checks for Kronos + Streamlit on ZERO.

Verifies the torchvision / torch stack that Streamlit's file watcher
probes after Kronos (or any transformers) load.  Missing torchvision
used to flood the console with ModuleNotFoundError spam from
``streamlit.watcher.local_sources_watcher.get_module_paths`` walking
``transformers`` lazy vision modules — weights still loaded; the spam
was non-fatal.

Streamlit-watcher caveats (remaining, even with torchvision installed)
----------------------------------------------------------------------
* ``.streamlit/config.toml`` sets ``server.fileWatcherType = "poll"``
  and blacklists ``.venv`` / site-packages.  Polling is slower to notice
  edits than native watchdog, but avoids Windows notify storms.
* ``ui.streamlit_boot`` (imported first from ``app.py``) patches
  ``get_module_paths`` to skip transformers/torch*/huggingface roots.
  If Streamlit renames that API, the patch no-ops and boot still works;
  vision-probe spam can return until the patch is updated.
* ``fileWatcherType = "none"`` kills auto-reload entirely (useful for
  locked-down demos, not for day-to-day UI work).
* HF Hub without ``HF_TOKEN`` still works for public NeoQuasar weights
  but may warn about rate limits on cold downloads.
* Do not force ``load()`` in CI without a warm HF cache — downloads are
  large.  This suite only asserts import + ``status()``; optional load
  is gated on cache presence.

Run with:  python -m pytest tests/test_kronos_runtime_deps.py -q
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_torchvision_imports_without_module_not_found():
    """torchvision must import cleanly (no ModuleNotFoundError)."""
    try:
        import torchvision  # noqa: F401
    except ModuleNotFoundError as exc:
        pytest.fail(f"torchvision ModuleNotFoundError: {exc}")
    assert torchvision.__version__


def test_torch_and_torchvision_versions_present():
    import torch
    import torchvision

    assert torch.__version__
    assert torchvision.__version__
    # CPU builds are expected on this workstation; don't require CUDA.
    assert "torch" in torch.__version__.lower() or torch.__version__[0].isdigit()


def test_kronos_service_status_never_loads_and_reports_torch():
    import engine.kronos_service as ks

    svc = ks.get_kronos_service()
    status = svc.status()
    assert isinstance(status, dict)
    assert status.get("torch_available") is True
    assert status.get("package_available") is True
    # status() must remain cheap — never mark model_loaded without load().
    assert status.get("model_loaded") is False
    assert status.get("error") in ("", None)


def test_streamlit_boot_watcher_guard_module_importable():
    """Boot guard exists so app.py can silence transformers path walks."""
    mod = importlib.import_module("ui.streamlit_boot")
    assert hasattr(mod, "apply_watcher_guards")
    assert callable(mod.apply_watcher_guards)
    # Idempotent; never raises.
    assert mod.apply_watcher_guards() in (True, False)


def test_streamlit_config_poll_watcher_present():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg = os.path.join(root, ".streamlit", "config.toml")
    assert os.path.isfile(cfg), ".streamlit/config.toml missing"
    text = open(cfg, encoding="utf-8").read()
    assert "fileWatcherType" in text
    assert "poll" in text


def test_optional_cached_load_only_when_explicitly_enabled():
    """Opt-in weight load: set KRONOS_TEST_LOAD=1 when HF cache is warm.

    Default suite stays offline/fast. Manual smoke already covers load()
    when cache exists; this gate avoids multi-minute CI / cold downloads.
    """
    if os.environ.get("KRONOS_TEST_LOAD", "").strip() not in ("1", "true", "yes"):
        pytest.skip("Set KRONOS_TEST_LOAD=1 to exercise cached load()")

    hub = os.path.expanduser(
        os.path.join("~", ".cache", "huggingface", "hub",
                     "models--NeoQuasar--Kronos-small")
    )
    if not os.path.isdir(hub):
        pytest.skip("HF Kronos-small cache not present; refusing cold download")

    import engine.kronos_service as ks

    svc = ks.get_kronos_service()
    ok = svc.load()
    assert ok is True
    assert svc.status().get("model_loaded") is True

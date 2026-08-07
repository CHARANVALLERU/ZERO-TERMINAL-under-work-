"""ZERO data layer — scrapers, caches, and market feeds.

Explicit package marker (not a PEP 420 namespace). Required so concurrent /
Streamlit-reload imports of ``data.*`` do not raise KeyError on submodule
names (e.g. ``data.global_feeds``).
"""

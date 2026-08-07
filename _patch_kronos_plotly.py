from pathlib import Path

charts = Path(r"D:\ZERO_FRESH\ui\kronos_charts.py")
t = charts.read_text(encoding="utf-8")

old_bt = (
    '        _apply_dark_layout(fig, title=_title("KRONOS BACKTEST"), height=520)\n'
    '        # Restyle the subplot titles to the muted terminal caption look.'
)
new_bt = (
    '        _apply_dark_layout(\n'
    '            fig,\n'
    '            title=_title("KRONOS BACKTEST"),\n'
    '            height=520,\n'
    '            uirevision="kronos-backtest",\n'
    '        )\n'
    '        # Restyle the subplot titles to the muted terminal caption look.'
)
if old_bt in t:
    t = t.replace(old_bt, new_bt)
    print("patched backtest uirevision")
elif 'uirevision="kronos-backtest"' in t:
    print("backtest uirevision already present")
else:
    print("WARN: backtest pattern not found")

old_all = (
    '__all__ = [\n'
    '    "kronos_forecast_chart",\n'
    '    "kronos_close_paths_chart",\n'
    '    "kronos_backtest_chart",\n'
    '    "kronos_status_badge_html",\n'
    ']'
)
new_all = (
    '__all__ = [\n'
    '    "kronos_forecast_chart",\n'
    '    "kronos_close_paths_chart",\n'
    '    "kronos_backtest_chart",\n'
    '    "kronos_status_badge_html",\n'
    '    "KRONOS_PLOTLY_CONFIG",\n'
    ']'
)
if old_all in t:
    t = t.replace(old_all, new_all)
    print("patched __all__")
elif '"KRONOS_PLOTLY_CONFIG"' in t[t.find("__all__"):]:
    print("__all__ already has KRONOS_PLOTLY_CONFIG")
else:
    print("WARN: __all__ pattern issue")

if "KRONOS_PLOTLY_CONFIG = dict(" not in t:
    print("WARN: KRONOS_PLOTLY_CONFIG missing from charts")
else:
    print("KRONOS_PLOTLY_CONFIG present")

charts.write_text(t, encoding="utf-8")
print("kronos_charts.py written")

panel = Path(r"D:\ZERO_FRESH\ui\kronos_panel.py")
pt = panel.read_text(encoding="utf-8")

replacements = [
(
'''        st.plotly_chart(fig, width='stretch', key="kronos_forecast_chart_fig",
                        config={"displayModeBar": False})''',
'''        _pcfg = getattr(charts, "KRONOS_PLOTLY_CONFIG", None) if charts else None
        st.plotly_chart(
            fig, width='stretch', key="kronos_forecast_chart_fig",
            config=_pcfg or dict(
                scrollZoom=True, displayModeBar=True, displaylogo=False,
            ),
        )'''
),
(
'''                st.plotly_chart(pfig, width='stretch', key="kronos_paths_chart_fig",
                                config={"displayModeBar": False})''',
'''                _pcfg = getattr(charts, "KRONOS_PLOTLY_CONFIG", None) if charts else None
                st.plotly_chart(
                    pfig, width='stretch', key="kronos_paths_chart_fig",
                    config=_pcfg or dict(
                        scrollZoom=True, displayModeBar=True, displaylogo=False,
                    ),
                )'''
),
(
'''            st.plotly_chart(bt_fig, width='stretch', key="kronos_bt_chart_fig",
                            config={"displayModeBar": False})''',
'''            _pcfg = getattr(charts, "KRONOS_PLOTLY_CONFIG", None) if charts else None
            st.plotly_chart(
                bt_fig, width='stretch', key="kronos_bt_chart_fig",
                config=_pcfg or dict(
                    scrollZoom=True, displayModeBar=True, displaylogo=False,
                ),
            )'''
),
]

for i, (old, new) in enumerate(replacements, 1):
    if old in pt:
        pt = pt.replace(old, new)
        print(f"patched panel call site {i}")
    elif "scrollZoom=True" in pt and "displayModeBar: False" not in pt.replace(" ", ""):
        # check individually
        if "displayModeBar\": False" in old and old.split("key=")[1].split(",")[0] in pt:
            print(f"WARN: call site {i} still old? checking...")
        print(f"call site {i}: old pattern absent (maybe already patched)")
    else:
        print(f"WARN: call site {i} pattern not found")

# Count remaining disabled modebars
disabled = pt.count('displayModeBar": False') + pt.count("displayModeBar': False")
print(f"remaining displayModeBar False: {disabled}")
panel.write_text(pt, encoding="utf-8")
print("kronos_panel.py written")

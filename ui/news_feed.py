import json
import html
import streamlit as st
import textwrap
import email.utils
from datetime import datetime, timezone

_GREEN = "#00ff88"
_RED = "#E50914"
_GOLD = "#D4AF37"
_GREY = "#666"


def _dir_color(direction):
    return {"BULLISH": _GREEN, "BEARISH": _RED}.get(direction, _GOLD)


def _impact_bar(score):
    color = _GREEN if score < 40 else (_GOLD if score < 70 else _RED)
    pct = max(2, min(100, score))
    return (f"<div style='height:4px;background:#1a1a1a;border-radius:2px;overflow:hidden;'>"
            f"<div style='height:100%;width:{pct}%;background:{color};'></div></div>")


def _get_published_ago(published_str):
    if not published_str:
        return ""
    try:
        # standard RSS/RFC 2822 format (e.g. "Wed, 15 Jul 2026 11:40:38 +0530")
        pub_dt = email.utils.parsedate_to_datetime(published_str)
        now = datetime.now(pub_dt.tzinfo or timezone.utc)
        diff = now - pub_dt
        minutes = int(diff.total_seconds() // 60)
        if minutes < 1:
            return "JUST NOW"
        if minutes < 60:
            return f"{minutes}M AGO"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}H AGO"
        days = hours // 24
        return f"{days}D AGO"
    except Exception:
        try:
            pub_dt = datetime.fromisoformat(published_str)
            diff = datetime.now(pub_dt.tzinfo) - pub_dt
            minutes = int(diff.total_seconds() // 60)
            if minutes < 1:
                return "JUST NOW"
            if minutes < 60:
                return f"{minutes}M AGO"
            hours = minutes // 60
            if hours < 24:
                return f"{hours}H AGO"
            days = hours // 24
            return f"{days}D AGO"
        except Exception:
            return ""


# ---------------------------------------------------------------------------
#  Breaking banner
# ---------------------------------------------------------------------------
def render_breaking_banner(breaking):
    """Red alert strip shown at the very top when a high-impact story lands."""
    if not breaking:
        return
    top = breaking[0]
    color = _dir_color(top["direction"])
    nifty = (top.get("per_index") or {}).get("NIFTY 50") or {}
    extra = f" · +{len(breaking) - 1} more" if len(breaking) > 1 else ""
    
    banner_html = f"""<div style="border:1px solid {color}; background:linear-gradient(90deg, rgba(229,9,20,0.12), rgba(0,0,0,0));
border-radius:6px; padding:14px 18px; margin-bottom:18px;
display:flex; align-items:center; gap:14px; animation:zeropulse 1.6s infinite;">
<span style="background:{color}; color:#000; font-weight:900; font-size:0.62rem;
letter-spacing:1.5px; padding:4px 9px; border-radius:3px;">● BREAKING</span>
<div style="flex:1; min-width:0;">
<div style="color:#fff; font-weight:700; font-size:0.9rem; white-space:nowrap;
overflow:hidden; text-overflow:ellipsis;">{html.escape(top['title'])}</div>
<div style="color:{color}; font-size:0.72rem; font-weight:700; margin-top:3px;">
{top['direction']} · {top['category_label']} · est. Nifty {nifty.get('move_pct', 0):+.2f}%
(~{nifty.get('move_points', 0):+.0f} pts) · impact {top['impact_score']:.0f}/100{extra}
</div>
</div>
</div>
<style>@keyframes zeropulse {{0%,100%{{box-shadow:0 0 0 0 rgba(229,9,20,0.0);}}
50%{{box-shadow:0 0 18px 0 rgba(229,9,20,0.35);}}}}</style>"""
    st.markdown(banner_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Live ticker
# ---------------------------------------------------------------------------
def render_news_ticker(feed, limit=12):
    """Slim horizontal auto-scrolling headline ribbon."""
    if not feed:
        return
    chips = []
    for it in feed[:limit]:
        c = _dir_color(it["direction"])
        arrow = "▲" if it["direction"] == "BULLISH" else ("▼" if it["direction"] == "BEARISH" else "•")
        chips.append(
            f"<span style='margin:0 26px; font-size:0.74rem; color:#ccc;'> "
            f"<span style='color:{c}; font-weight:800;'>{arrow} {it['category_label']}</span>"
            f"&nbsp;&nbsp;{html.escape(it['title'][:90])}"
            f"<span style='color:{c};'>&nbsp;&nbsp;{it['per_index'].get('NIFTY 50',{}).get('move_pct',0):+.2f}%</span>"
            f"</span>")
    stream = "".join(chips)
    
    ticker_html = f"""<div style="border-top:1px solid #1a1a1a; border-bottom:1px solid #1a1a1a;
overflow:hidden; white-space:nowrap; padding:9px 0; margin:6px 0 20px 0;
background:rgba(10,10,10,0.6);">
<div style="display:inline-block; padding-left:100%; animation:zeroticker 48s linear infinite;">
{stream}
</div>
</div>
<style>@keyframes zeroticker {{0%{{transform:translateX(0);}}100%{{transform:translateX(-100%);}}}}</style>"""
    st.markdown(ticker_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Flagship impact panel
# ---------------------------------------------------------------------------
def render_impact_panel(feed, title="GLOBAL MARKET INTELLIGENCE — LIVE IMPACT FEED", limit=18):
    """The main real-time news section: one impact card per headline."""
    st.markdown(
        f"<p class='gold-title'>{title}</p>"
        f"<p class='label-grey' style='margin:-6px 0 18px 0;'>Every global headline scored for its "
        f"estimated effect on Nifty / Bank Nifty / Sensex — updated in real time.</p>",
        unsafe_allow_html=True)

    if not feed:
        # Loading skeleton: grey shimmer placeholders so the first paint isn't blank.
        st.markdown("""
        <style>@keyframes zeroshimmer{0%{background-position:-450px 0}100%{background-position:450px 0}}
        .zsk{background:#0d0d0d;background-image:linear-gradient(90deg,#0d0d0d 0px,#1a1a1a 180px,#0d0d0d 360px);
        background-size:900px 100%;animation:zeroshimmer 1.2s linear infinite;border-radius:4px;}</style>
        """, unsafe_allow_html=True)
        for _ in range(3):
            skeleton_html = """<div class="digital-card" style="margin-bottom:14px;padding:16px 18px;">
<div class="zsk" style="height:12px;width:38%;margin-bottom:12px;"></div>
<div class="zsk" style="height:16px;width:88%;margin-bottom:8px;"></div>
<div class="zsk" style="height:16px;width:64%;margin-bottom:14px;"></div>
<div class="zsk" style="height:4px;width:100%;"></div>
</div>"""
            st.markdown(skeleton_html, unsafe_allow_html=True)
        return

    # Build the HTML content of the actual cards
    cards_html = []
    for it in feed[:limit]:
        color = _dir_color(it["direction"])
        arrow = "▲" if it["direction"] == "BULLISH" else ("▼" if it["direction"] == "BEARISH" else "•")
        new_tag = ("<span style='background:#E50914;color:#fff;font-size:0.55rem;font-weight:900;"
                   "padding:2px 6px;border-radius:2px;letter-spacing:1px;margin-right:8px;'>NEW</span>"
                   ) if it.get("is_new") else ""
        per = it.get("per_index") or {}
        
        def cell_html(idx, short):
            v = per.get(idx) or {}
            if not isinstance(v, dict):
                v = {}
            pc = v.get("move_pct", 0.0)
            cc = _GREEN if pc > 0 else (_RED if pc < 0 else _GREY)
            return (f"<div style='text-align:center;flex:1;'>"
                    f"<div style='color:#555;font-size:0.55rem;letter-spacing:1px;'>{short}</div>"
                    f"<div style='color:{cc};font-weight:800;font-size:0.9rem;'>{pc:+.2f}%</div>"
                    f"<div style='color:#444;font-size:0.55rem;'>{v.get('move_points',0) or 0:+.0f}</div></div>")

        link = it.get("link") or ""
        link_html = (f"<a href='{html.escape(link)}' target='_blank' style='text-decoration:none;color:{_RED};"
                     f"font-size:0.6rem;font-weight:800;border:1px solid {_RED};padding:2px 8px;"
                     f"border-radius:2px;'>READ SOURCE</a>") if link else ""

        # Calculate time difference
        pub_ago = _get_published_ago(it.get("published", ""))
        ago_html = f" · {pub_ago}" if pub_ago else ""

        card = f"""<div class="digital-card" style="margin-bottom:14px; padding:16px 18px;">
<div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
<div style="flex:1; min-width:0;">
<div style="margin-bottom:6px;">
{new_tag}
<span style="color:{color}; font-weight:800; font-size:0.6rem; letter-spacing:1px; border:1px solid {color}; padding:2px 7px; border-radius:2px;">{arrow} {it['direction']}</span>
<span style="color:{_GOLD}; font-size:0.6rem; font-weight:700; letter-spacing:1px; margin-left:8px;">{it['category_label']}</span>
<span style="color:#444; font-size:0.58rem; margin-left:8px;">{html.escape(it.get('source',''))}{ago_html}</span>
</div>
<div style="color:#fff; font-size:0.9rem; line-height:1.55; font-weight:600;">{html.escape(it['title'])}</div>
</div>
<div style="text-align:right; min-width:70px;">
<div style="color:#555; font-size:0.55rem; letter-spacing:1px;">IMPACT</div>
<div style="color:{color}; font-weight:900; font-size:1.25rem;">{it['impact_score']:.0f}</div>
<div style="color:#444; font-size:0.55rem;">CONF {it['confidence']:.0f}%</div>
</div>
</div>
<div style="margin:12px 0 10px 0;">{_impact_bar(it['impact_score'])}</div>
<div style="display:flex; gap:6px; border-top:1px solid #141414; padding-top:10px;">
{cell_html('NIFTY 50','NIFTY')}{cell_html('BANKNIFTY','BANKNIFTY')}{cell_html('SENSEX','SENSEX')}
<div style="display:flex; align-items:center;">{link_html}</div>
</div>
</div>"""
        cards_html.append(card)

    all_cards_str = "\n".join(cards_html)
    st.markdown(all_cards_str, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Device notifications (real OS/browser popups)
# ---------------------------------------------------------------------------
def push_device_notifications(breaking):
    """Fire real device notifications for breaking items via the Web
    Notifications API, and an in-app toast as a guaranteed fallback.

    Works like a normal news site: the browser asks permission once, then
    each breaking story pops up on the device even if the tab is backgrounded.
    """
    if not breaking:
        return

    # In-app toasts (always visible inside the app).
    for b in breaking[:3]:
        nifty = (b.get("per_index") or {}).get("NIFTY 50") or {}
        icon = "🔴" if b["direction"] == "BEARISH" else ("🟢" if b["direction"] == "BULLISH" else "🟡")
        try:
            st.toast(
                f"{icon} BREAKING · {b['category_label']}\n{b['title'][:80]}\n"
                f"Est. Nifty {nifty.get('move_pct',0):+.2f}% (~{nifty.get('move_points',0):+.0f} pts)",
                icon="🔔")
        except Exception:
            pass

    # Real browser/OS notifications.
    payload = [{
        "title": f"🔴 ZERO ALERT · {b['category_label']}" if b["direction"] == "BEARISH"
                 else f"🟢 ZERO ALERT · {b['category_label']}",
        "body": (f"{b['title']}\n"
                 f"Est. Nifty {((b.get('per_index') or {}).get('NIFTY 50') or {}).get('move_pct', 0):+.2f}% "
                 f"(~{((b.get('per_index') or {}).get('NIFTY 50') or {}).get('move_points', 0):+.0f} pts) · "
                 f"{b['direction']} · impact {b['impact_score']:.0f}/100"),
        "tag": b["id"],
    } for b in breaking[:5]]

    data = json.dumps(payload)
    st.iframe(f"""
    <script>
    (function() {{
        const items = {data};
        function fire() {{
            items.forEach(function(n) {{
                try {{ new Notification(n.title, {{ body: n.body, tag: n.tag, requireInteraction: false }}); }}
                catch (e) {{}}
            }});
        }}
        if (!("Notification" in window)) return;
        if (Notification.permission === "granted") {{ fire(); }}
        else if (Notification.permission !== "denied") {{
            Notification.requestPermission().then(function(p) {{ if (p === "granted") fire(); }});
        }}
    }})();
    </script>
    """, height=1)


def request_notification_permission():
    """Politely prompt for notification permission once, up front."""
    st.iframe("""
    <script>
    if (("Notification" in window) && Notification.permission === "default") {
        Notification.requestPermission();
    }
    </script>
    """, height=1)


def render_autorefresh(seconds):
    """DEPRECATED — was a hard page-reload every N seconds. The terminal now
    uses `silent_news_tick` (background re-fetch, no page reload). Kept as a
    no-op stub for one release in case external callers still import it."""
    return None


def silent_news_tick(seconds, on_tick_value="tick"):
    """Lightweight client-side ticker that does NOT reload the page.

    Every `seconds`, the iframe sends a no-op value back to the Streamlit
    component so the server re-evaluates the page. Combined with
    `st.cache_data(ttl=seconds)` on the news and matrix fetchers, this gives
    the user continuously-fresh values without ever interrupting their
    scroll/click. The server-side handler in `app.py` watches
    `st.session_state['_last_tick']` to detect the tick and show a
    "Quant cores calibrated" toast when the market is open and the band
    shifted materially.
    """
    try:
        st.iframe(f"""
        <script>
        (function() {{
          try {{
            var Streamlit = (window.parent && window.parent.Streamlit) || window.Streamlit;
            if (!Streamlit || !Streamlit.setComponentValue) return;
            setInterval(function() {{
              try {{
                Streamlit.setComponentValue({{
                  type: {json.dumps(on_tick_value)},
                  t: Date.now()
                }});
              }} catch (e) {{}}
            }}, {int(seconds) * 1000});
          }} catch (e) {{}}
        }})();
        </script>
        """, height=1)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  Client-side enhancements (run in an iframe, act on the parent document).
# ---------------------------------------------------------------------------
def enable_dig_dive_hotkey():
    """Enter or Space triggers the DIG & DIVE button — single-keystroke entry."""
    st.iframe("""
    <script>
    (function(){
      const doc = window.parent.document;
      if (doc.__zeroHotkey) return; doc.__zeroHotkey = true;
      doc.addEventListener('keydown', function(e){
        if (e.key === 'Enter' || e.key === ' ') {
          const b = [...doc.querySelectorAll('button')].find(x => x.innerText.trim() === 'DIG & DIVE');
          if (b) { e.preventDefault(); b.click(); }
        }
      });
    })();
    </script>""", height=1)


def persist_active_tab():
    """Remember the active tab across auto-refreshes (sessionStorage)."""
    st.iframe("""
    <script>
    (function(){
      const doc = window.parent.document;
      function tabs(){ return doc.querySelectorAll('button[data-baseweb="tab"]'); }
      function restore(){
        const t = tabs(); if(!t.length) return false;
        const s = sessionStorage.getItem('zero_tab');
        if (s !== null && t[s] && t[s].getAttribute('aria-selected') !== 'true') t[s].click();
        t.forEach((el,i)=>{ if(!el.__zt){ el.__zt=true; el.addEventListener('click',()=>sessionStorage.setItem('zero_tab',i)); }});
        return true;
      }
      let n=0; const iv=setInterval(()=>{ if(restore()||n++>20) clearInterval(iv); }, 150);
    })();
    </script>""", height=1)


def tab_unread_badge(count, tab_index=3):
    """Red badge on the GLOBAL NEWS tab for unread breaking items; clears on visit."""
    st.iframe(f"""
    <script>
    (function(){{
      const doc = window.parent.document, count = {int(count)}, ti = {int(tab_index)};
      let tries=0; const iv=setInterval(()=>{{
        const tabs = doc.querySelectorAll('button[data-baseweb="tab"]');
        if(!tabs.length){{ if(tries++>20) clearInterval(iv); return; }}
        clearInterval(iv);
        const t = tabs[ti]; if(!t) return;
        let b = t.querySelector('.zero-badge');
        if(count>0){{
          if(!b){{ b=doc.createElement('span'); b.className='zero-badge';
            b.style.cssText='background:#E50914;color:#fff;font-size:0.55rem;font-weight:900;border-radius:9px;padding:1px 6px;margin-left:7px;';
            t.appendChild(b); }}
          b.textContent = count;
          if(!t.__zbadge){{ t.__zbadge=true; t.addEventListener('click',()=>{{const x=t.querySelector('.zero-badge'); if(x) x.remove();}}); }}
        }} else if(b) b.remove();
      }}, 150);
    }})();
    </script>""", height=1)


def status_pill(next_refresh_secs, last_fetch_age_secs=0, healthy=True):
    """Fixed corner pill: live status + countdown to next auto-refresh."""
    dot = "#00ff88" if healthy else "#E50914"
    # Cosmetic: show "just now" for the first few seconds so the pill
    # doesn't read "0s ago" right after a refresh.
    age_disp = "just now" if int(last_fetch_age_secs) < 5 else f"{int(last_fetch_age_secs)}s"
    st.iframe(f"""
    <div id="zero-pill" style="position:fixed;top:10px;right:14px;z-index:99999;
        background:rgba(10,10,10,0.85);border:1px solid #222;border-radius:20px;
        padding:5px 12px;font-family:Inter,sans-serif;font-size:0.62rem;color:#aaa;
        display:flex;align-items:center;gap:8px;backdrop-filter:blur(4px);">
      <span style="width:7px;height:7px;border-radius:50%;background:{dot};
            box-shadow:0 0 6px {dot};display:inline-block;"></span>
      <span>NEWS <b id="zp-age" style="color:#ddd;">{age_disp}</b> ago</span>
      <span style="color:#333;">|</span>
      <span>refresh in <b id="zp-cd" style="color:#D4AF37;">{int(next_refresh_secs)}s</b></span>
    </div>
    <script>
    (function(){{
      const doc = window.parent.document;
      const host = doc.getElementById('zero-pill');
      let cd={int(next_refresh_secs)}, age={int(last_fetch_age_secs)};
      const el=document.getElementById('zp-cd'), ae=document.getElementById('zp-age');
      setInterval(()=>{{
        cd=Math.max(0,cd-1); age++;
        if(el)el.textContent=cd+'s';
        if(ae)ae.textContent=(age<5?'just now':age+'s');
      }},1000);
    }})();
    </script>""", height=44)

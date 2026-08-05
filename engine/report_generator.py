"""ZERO deterministic daily Investment-Committee (IC) memo generator.

Renders the ZERO daily prediction matrix (produced by
``engine.prediction_matrix.generate_prediction_matrix``) into a FinRobot-style
Investment Committee memo written in Obsidian-flavoured markdown, matching the
vault conventions found under ``obsidian_vault/`` (flat YAML frontmatter with
inline lists, wikilinks such as ``[[ZERO]]`` / ``[[ZERO Brain Engine]]``).

Design contract
---------------
* Pure standard library only (``os``, ``datetime``, ``logging``, ``typing``).
  No Streamlit, no network, no third-party imports — the module is importable
  in any context (CLI, scheduler, tests).
* Fully deterministic: it takes pre-computed dicts and renders markdown.
  LLM narration is intentionally out of scope.
* Defensive: missing or malformed keys never raise — affected values degrade
  to ``n/a`` and whole sections degrade to a single ``n/a`` line.
* Constants live at module top and are env-overridable (``ZERO_MEMO_*``).

Public API
----------
* ``generate_daily_memo(matrix, debate=None, trade_date=None, extra=None)`` ->
  markdown string.
* ``write_memo_to_vault(markdown, trade_date, vault_dir=DEFAULT_VAULT_DIR)`` ->
  path written (idempotent same-day overwrite).
* ``memo_from_latest(matrix=None, debate=None)`` -> generate + write for
  today, returns the vault path.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Iterator

logger = logging.getLogger('ZERO_REPORT_GENERATOR')

# ---------------------------------------------------------------------------
# Constants (env-overridable)
# ---------------------------------------------------------------------------

DEFAULT_VAULT_DIR: str = os.environ.get(
    'ZERO_MEMO_VAULT_DIR', 'obsidian_vault/01_Daily_Logs'
)
"""Default vault folder for daily IC memos."""

MEMO_FILE_SUFFIX: str = os.environ.get('ZERO_MEMO_FILE_SUFFIX', 'ZERO-Memo')
"""File-name suffix: ``<YYYY-MM-DD>-<MEMO_FILE_SUFFIX>.md``."""

VIX_RISK_THRESHOLD: float = float(os.environ.get('ZERO_MEMO_VIX_THRESHOLD', '20'))
"""India VIX level above which volatility is flagged as a key risk."""

CONFIDENCE_THRESHOLD: float = float(
    os.environ.get('ZERO_MEMO_CONFIDENCE_THRESHOLD', '60')
)
"""Engine confidence (%) below which an index is flagged as low conviction."""

EXTREME_SENTIMENT_THRESHOLD: float = float(
    os.environ.get('ZERO_MEMO_SENTIMENT_THRESHOLD', '0.5')
)
"""Absolute news-sentiment score at/above which sentiment is flagged extreme."""

NEWS_SHIFT_FLAG_THRESHOLD: float = float(
    os.environ.get('ZERO_MEMO_NEWS_SHIFT_THRESHOLD', '25')
)
"""Absolute news repricing (points) at/above which the shift is flagged."""

MAX_HEADLINES: int = int(os.environ.get('ZERO_MEMO_MAX_HEADLINES', '5'))
"""Maximum number of latest-news headlines rendered in Evidence & Drivers."""

INDEX_ORDER: tuple[str, ...] = ('NIFTY 50', 'BANKNIFTY', 'SENSEX')
"""Preferred display order for known indices; unknown extras follow."""

NA: str = 'n/a'
"""Fallback token for missing/malformed values."""

_NON_INDEX_KEYS: frozenset[str] = frozenset({
    'latest_news', 'sentiment_data', 'news_overlay', 'error', 'metadata',
    'generated_at', 'date', 'trade_date',
})
"""Top-level matrix keys that are not per-index prediction dicts."""

DISCLAIMER_TEXT: str = (
    'This memo is generated deterministically from the ZERO prediction matrix '
    'for research and educational purposes only. It is not investment advice, '
    'a solicitation, or a recommendation to buy or sell any security or '
    'derivative. Trading equities and derivatives carries substantial risk of '
    'loss. Consult a SEBI-registered investment adviser before acting on any '
    'information contained herein.'
)

__all__ = [
    'DEFAULT_VAULT_DIR',
    'generate_daily_memo',
    'write_memo_to_vault',
    'memo_from_latest',
]

# ---------------------------------------------------------------------------
# Defensive formatting helpers (never raise)
# ---------------------------------------------------------------------------


def _is_num(value: Any) -> bool:
    """True for real numeric values (excludes bools)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_dict(value: Any) -> dict:
    """Return value if it is a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    """Return value as a list if list/tuple, else an empty list."""
    return list(value) if isinstance(value, (list, tuple)) else []


def _fmt_num(value: Any, nd: int = 2) -> str:
    """Format a number with thousands separators, else ``n/a``."""
    if not _is_num(value):
        return NA
    return f"{float(value):,.{nd}f}"


def _fmt_pct(value: Any, nd: int = 1) -> str:
    """Format a percentage value, else ``n/a``."""
    if not _is_num(value):
        return NA
    return f"{float(value):.{nd}f}%"


def _fmt_band(lo: Any, hi: Any) -> str:
    """Format a conformal band as ``lo–hi``, else ``n/a``."""
    if not _is_num(lo) or not _is_num(hi):
        return NA
    return f"{float(lo):,.2f}–{float(hi):,.2f}"


def _cell(text: Any) -> str:
    """Sanitize a value for use inside a markdown table cell."""
    return str(text).replace('|', '\\|').replace('\n', ' ').strip()


def _headline(item: Any) -> str:
    """Extract printable headline text from a news item (str or dict)."""
    if isinstance(item, str):
        return item.strip() or NA
    if isinstance(item, dict):
        for key in ('title', 'headline', 'text', 'summary', 'news'):
            val = item.get(key)
            if val:
                return str(val).strip()
        return str(item)
    return str(item)


def _factor_text(item: Any) -> str:
    """Extract printable text for a sentiment factor entry."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ('factor', 'name', 'label', 'title', 'reason'):
            val = item.get(key)
            if val:
                return str(val).strip()
        return str(item)
    return str(item)


def _yaml_scalar(value: Any) -> str:
    """Serialize a scalar in the vault's flat-YAML frontmatter style."""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return str(value).lower()
    if _is_num(value):
        return f"{value}"
    return "'" + str(value).replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Matrix introspection
# ---------------------------------------------------------------------------


def _iter_indices(matrix: dict) -> Iterator[tuple[str, dict]]:
    """Yield ``(index_name, prediction_dict)`` pairs in stable display order.

    Known indices follow ``INDEX_ORDER``; any extra dict entries that look
    like per-index predictions (they carry ``pred_open`` or ``prev_close``)
    are appended afterwards. Entries carrying an ``error`` key are skipped.
    """
    matrix = _as_dict(matrix)
    seen: set[str] = set()
    for name in INDEX_ORDER:
        data = matrix.get(name)
        if isinstance(data, dict) and 'error' not in data:
            seen.add(name)
            yield name, data
    for name, data in matrix.items():
        if name in seen or name in _NON_INDEX_KEYS:
            continue
        if (
            isinstance(data, dict)
            and 'error' not in data
            and ('pred_open' in data or 'prev_close' in data)
        ):
            yield name, data


def _side_bucket(movement_side: Any) -> str:
    """Classify a ``movement_side`` label into bullish / bearish / neutral."""
    text = str(movement_side or '').lower()
    if 'bull' in text:
        return 'bullish'
    if 'bear' in text:
        return 'bearish'
    return 'neutral'


def _first_value(indices: list[tuple[str, dict]], key: str) -> Any:
    """First non-None value for ``key`` across index prediction dicts."""
    for _, data in indices:
        value = data.get(key)
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_frontmatter(
    matrix: dict,
    indices: list[tuple[str, dict]],
    trade_date: str,
    extra: dict | None,
) -> str:
    """YAML frontmatter matching the vault daily-log style + memo tags."""
    lines = ['---']
    lines.append(f'aliases: [{trade_date} ZERO IC Memo, ZERO Daily Memo {trade_date}]')
    lines.append('tags: [zero, daily-memo]')
    lines.append('type: daily_memo')
    lines.append(f"date: '{trade_date}'")
    names = [name for name, _ in indices]
    if names:
        lines.append('indices: [' + ', '.join(names) + ']')

    # Daily-log parity fields (see Templates/daily_template.md).
    nifty = matrix.get('NIFTY 50')
    if isinstance(nifty, dict):
        low, high = nifty.get('pred_low'), nifty.get('pred_high')
        if _is_num(low) and _is_num(high):
            lines.append(f'nifty_range: [{low}, {high}]')
        if _is_num(nifty.get('confidence')):
            lines.append(f"nifty_confidence: {nifty['confidence']}")

    # Forward-compat escape hatch: simple scalars/lists land in frontmatter.
    for key, value in _as_dict(extra).items():
        key = str(key).strip()
        if not key or ':' in key:
            continue
        if isinstance(value, (list, tuple)):
            items = ', '.join(_yaml_scalar(v) for v in value)
            lines.append(f'{key}: [{items}]')
        else:
            lines.append(f'{key}: {_yaml_scalar(value)}')

    lines.append('---')
    return '\n'.join(lines)


def _build_executive_summary(indices: list[tuple[str, dict]]) -> str:
    """3-5 deterministic synthesis bullets: lean, conviction, key risks."""
    lines = ['## Executive Summary', '']
    if not indices:
        lines.append(f'- {NA} — no index predictions available for this session.')
        return '\n'.join(lines)

    buckets = {'bullish': [], 'bearish': [], 'neutral': []}  # type: dict[str, list[str]]
    for name, data in indices:
        buckets[_side_bucket(data.get('movement_side'))].append(name)

    n_bull, n_bear, n_neut = (
        len(buckets['bullish']),
        len(buckets['bearish']),
        len(buckets['neutral']),
    )
    if n_bull > n_bear:
        lean = 'BULLISH'
    elif n_bear > n_bull:
        lean = 'BEARISH'
    else:
        lean = 'NEUTRAL / MIXED'
    lines.append(
        f'- **Directional lean:** {lean} — {n_bull} bullish / {n_bear} bearish '
        f'/ {n_neut} neutral across {len(indices)} indices.'
    )

    best: tuple[str, float, Any] | None = None
    for name, data in indices:
        conf = data.get('confidence')
        if _is_num(conf) and (best is None or float(conf) > best[1]):
            best = (name, float(conf), data.get('movement_side'))
    if best is not None:
        lines.append(
            f'- **Strongest conviction:** {best[0]} — engine confidence '
            f'{_fmt_pct(best[1])} ({best[2] or NA}).'
        )
    else:
        lines.append(
            f'- **Strongest conviction:** {NA} — engine confidence scores unavailable.'
        )

    risks: list[str] = []
    vix_vals = [
        (name, float(data['vix']))
        for name, data in indices
        if _is_num(data.get('vix'))
    ]
    if vix_vals:
        vix_name, vix_max = max(vix_vals, key=lambda pair: pair[1])
        if vix_max > VIX_RISK_THRESHOLD:
            risks.append(
                f'India VIX {vix_max:,.1f} above the {VIX_RISK_THRESHOLD:g} '
                f'threshold (via {vix_name}) — elevated volatility regime'
            )
    sent_vals = [
        float(data['sentiment_score'])
        for _, data in indices
        if _is_num(data.get('sentiment_score'))
    ]
    if sent_vals:
        sent_max = max(sent_vals, key=abs)
        if abs(sent_max) >= EXTREME_SENTIMENT_THRESHOLD:
            risks.append(
                f'extreme news sentiment {sent_max:+.2f} '
                f'(|score| >= {EXTREME_SENTIMENT_THRESHOLD:g}) — '
                f'sentiment-driven whipsaw risk'
            )
    shift_vals = [
        (name, abs(float(data['news_shift_points'])))
        for name, data in indices
        if _is_num(data.get('news_shift_points'))
    ]
    if shift_vals:
        shift_name, shift_max = max(shift_vals, key=lambda pair: pair[1])
        if shift_max >= NEWS_SHIFT_FLAG_THRESHOLD:
            risks.append(
                f'large overnight news repricing on {shift_name} '
                f'({shift_max:,.1f} pts shift)'
            )

    if risks:
        lines.append(f'- **Key risk:** {risks[0]}.')
        for extra_risk in risks[1:]:
            lines.append(f'- **Additional risk:** {extra_risk}.')
    else:
        lines.append(
            '- **Key risk:** none flagged — VIX, sentiment, and news-shift '
            'readings within normal bounds.'
        )
    return '\n'.join(lines)


def _build_prediction_matrix(indices: list[tuple[str, dict]]) -> str:
    """One markdown table across indices with calibrated open bands."""
    lines = ['## Prediction Matrix', '']
    if not indices:
        lines.append(f'{NA} — no prediction rows available.')
        return '\n'.join(lines)

    lines.append(
        '| Index | Prev Close | Pred Open (band) | Pred High | Pred Low | '
        'Pred Close | Confidence | Side | News Shift (pts) |'
    )
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for name, data in indices:
        pred_open = _fmt_num(data.get('pred_open'))
        band = _fmt_band(data.get('open_lo'), data.get('open_hi'))
        open_cell = f'{pred_open} ({band})' if band != NA else pred_open
        row = [
            name,
            _fmt_num(data.get('prev_close')),
            open_cell,
            _fmt_num(data.get('pred_high')),
            _fmt_num(data.get('pred_low')),
            _fmt_num(data.get('pred_close')),
            _fmt_pct(data.get('confidence')),
            str(data.get('movement_side') or NA),
            _fmt_num(data.get('news_shift_points'), nd=1),
        ]
        lines.append('| ' + ' | '.join(_cell(col) for col in row) + ' |')
    lines.append('')
    lines.append('*Pred Open band = calibrated conformal open_lo–open_hi interval.*')
    return '\n'.join(lines)


def _build_evidence(matrix: dict, indices: list[tuple[str, dict]]) -> str:
    """Macro drivers (GIFT Nifty, VIX, ADR, PCR, sentiment) + top headlines."""
    lines = ['## Evidence & Drivers', '']

    gift = _first_value(indices, 'gift_nifty')
    lines.append(f'- **GIFT Nifty:** {_fmt_num(gift)}')
    lines.append(f'- **India VIX:** {_fmt_num(_first_value(indices, "vix"), nd=1)}')
    lines.append(f'- **ADR delta:** {_fmt_num(_first_value(indices, "adr_delta"))}')
    lines.append(f'- **PCR (options):** {_fmt_num(_first_value(indices, "pcr"))}')

    factors: list = []
    for _, data in indices:
        factors = _as_list(data.get('sentiment_factors'))
        if factors:
            break
    factor_text = (
        ', '.join(_factor_text(f) for f in factors[:5]) if factors else NA
    )
    sentiment = _first_value(indices, 'sentiment_score')
    lines.append(
        f'- **News sentiment score:** {_fmt_num(sentiment)} '
        f'— dominant factors: {factor_text}'
    )

    lines.append('')
    lines.append('**Top headlines:**')
    news = _as_list(matrix.get('latest_news'))
    if news:
        for item in news[:MAX_HEADLINES]:
            lines.append(f'- {_cell(_headline(item))}')
    else:
        lines.append(f'- {NA} — no headlines captured for this session.')
    return '\n'.join(lines)


def _build_consensus_strategy(indices: list[tuple[str, dict]]) -> str:
    """Per-index agent consensus mini-table, quant setup, Nautilus suggestion."""
    lines = ['## Agent Consensus & Strategy', '']
    rendered = False

    for name, data in indices:
        consensus = _as_dict(data.get('agent_consensus'))
        strategy = _as_dict(data.get('quant_strategy'))
        nautilus = _as_dict(data.get('nautilus_order_suggestion'))
        if not (consensus or strategy or nautilus):
            continue
        rendered = True
        lines.append(f'### {name}')

        if consensus:
            lines.append(
                f"**Consensus:** {consensus.get('verdict', NA)} "
                f"(score {_fmt_num(consensus.get('consensus_score'))}, "
                f"confidence {_fmt_pct(consensus.get('overall_confidence'))})"
            )
            agents = _as_dict(consensus.get('agents'))
            if agents:
                lines.append('')
                lines.append('| Agent | Bias | Score | Confidence |')
                lines.append('|---|---|---|---|')
                for agent_key in ('fundamental', 'technical', 'sentiment', 'risk'):
                    agent = _as_dict(agents.get(agent_key))
                    if not agent:
                        continue
                    agent_name = agent.get('agent', agent_key.title())
                    agent_bias = agent.get('bias', agent.get('risk_rating', NA))
                    lines.append(
                        f"| {_cell(agent_name)} | {_cell(agent_bias)} | "
                        f"{_fmt_num(agent.get('score'))} | "
                        f"{_fmt_pct(agent.get('confidence'))} |"
                    )
                lines.append('')

        if strategy:
            lines.append(
                f"**Quant Strategy:** {strategy.get('regime_label', NA)} — "
                f"{strategy.get('strategy_name', NA)} | "
                f"R:R {strategy.get('risk_reward_ratio', NA)} | "
                f"Win Prob {_fmt_pct(strategy.get('win_probability_pct'))}"
            )

        if nautilus:
            side = str(nautilus.get('suggested_side', NA))
            if _is_num(nautilus.get('take_profit')) or _is_num(nautilus.get('stop_loss')):
                lines.append(
                    f'**Nautilus Order Suggestion:** {side} — entry guide '
                    f"{_fmt_num(nautilus.get('entry_price_guide'))} | "
                    f"TP {_fmt_num(nautilus.get('take_profit'))} | "
                    f"SL {_fmt_num(nautilus.get('stop_loss'))}"
                )
            else:
                message = nautilus.get('message')
                suffix = f' — {message}' if message else ''
                lines.append(f'**Nautilus Order Suggestion:** {side}{suffix}')

        lines.append('')

    if not rendered:
        lines.append(
            f'{NA} — agent consensus, quant strategy, and order suggestions '
            f'unavailable for this session.'
        )
    return '\n'.join(lines).rstrip()


def _build_debate_verdict(debate: dict) -> str:
    """FinRobot-style PM debate verdict (only rendered when debate is passed)."""
    pm = debate.get('pm_verdict')
    pm = pm if isinstance(pm, dict) else debate
    lines = ['## Debate Verdict', '']
    lines.append(f"- **Action:** {pm.get('action', NA)}")
    lines.append(f"- **Conviction:** {pm.get('conviction', NA)}")
    lines.append(f"- **Kill Condition:** {pm.get('kill_condition', NA)}")
    lines.append(f"- **Reasoning:** {pm.get('reasoning', NA)}")
    lines.append(f"- **Risk Level:** {debate.get('risk_level', pm.get('risk_level', NA))}")
    return '\n'.join(lines)


def _build_risk_section(indices: list[tuple[str, dict]]) -> str:
    """Per-index thesis-invalidation lines + portfolio confidence cautions."""
    lines = ['## Risk & Kill Conditions', '']
    if not indices:
        lines.append(f'- {NA} — no index theses to invalidate.')
    for name, data in indices:
        lines.append(
            f'- **{name}:** thesis invalid on sustained trade beyond '
            f"{_fmt_num(data.get('pred_low'))} / {_fmt_num(data.get('pred_high'))} "
            f'(pred_low / pred_high envelope).'
        )

    lines.append('')
    lines.append(
        f'**Portfolio-level cautions (confidence < {CONFIDENCE_THRESHOLD:g}%):**'
    )
    cautions = []
    for name, data in indices:
        conf = data.get('confidence')
        if _is_num(conf) and float(conf) < CONFIDENCE_THRESHOLD:
            cautions.append(
                f'- **{name}** engine confidence {_fmt_pct(conf)} — treat signals '
                f'as low conviction; reduce size or stand aside.'
            )
    if cautions:
        lines.extend(cautions)
    else:
        lines.append(
            '- None — all index confidence scores at/above threshold or unavailable.'
        )
    return '\n'.join(lines)


def _build_footer() -> str:
    """Vault-style footer wikilinks back to the core graph hubs."""
    return (
        '---\n\n'
        '**Related:** [[ZERO]] | [[ZERO Brain Engine]]\n\n'
        '*Generated by ZERO Engine — deterministic daily IC memo.*'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_daily_memo(
    matrix: dict,
    debate: dict | None = None,
    trade_date: str | None = None,
    extra: dict | None = None,
) -> str:
    """Render the daily IC memo markdown from a pre-computed prediction matrix.

    Parameters
    ----------
    matrix:
        Prediction matrix dict as returned by
        ``engine.prediction_matrix.generate_prediction_matrix`` — per-index
        dicts (``NIFTY 50`` / ``BANKNIFTY`` / ``SENSEX``) plus top-level
        ``latest_news`` / ``sentiment_data``. Malformed input degrades to
        ``n/a`` sections rather than raising.
    debate:
        Optional FinRobot-style debate outcome dict with a ``pm_verdict``
        sub-dict (``action`` / ``conviction`` / ``kill_condition`` /
        ``reasoning``) and ``risk_level``. When omitted, the Debate Verdict
        section is skipped entirely.
    trade_date:
        ``YYYY-MM-DD`` date string; defaults to today (local date).
    extra:
        Optional dict of simple scalar/list values merged into the memo
        frontmatter (forward-compat escape hatch).

    Returns
    -------
    str
        The complete markdown memo, including vault-style YAML frontmatter.
    """
    matrix = _as_dict(matrix)
    trade_date = str(trade_date).strip() if trade_date else datetime.date.today().isoformat()
    indices = list(_iter_indices(matrix))

    sections = [
        _build_frontmatter(matrix, indices, trade_date, extra),
        f'# ZERO Daily IC Memo — {trade_date}',
        _build_executive_summary(indices),
        _build_prediction_matrix(indices),
        _build_evidence(matrix, indices),
        _build_consensus_strategy(indices),
    ]
    if isinstance(debate, dict) and debate:
        sections.append(_build_debate_verdict(debate))
    sections.append(_build_risk_section(indices))
    sections.append(f'## Disclaimer\n\n{DISCLAIMER_TEXT}')
    sections.append(_build_footer())

    return '\n\n'.join(section.strip('\n') for section in sections if section) + '\n'


def write_memo_to_vault(
    markdown: str,
    trade_date: str,
    vault_dir: str = DEFAULT_VAULT_DIR,
) -> str:
    """Write the memo to ``<vault_dir>/<YYYY-MM-DD>-ZERO-Memo.md``.

    Creates the directory if needed and overwrites any existing same-day memo
    (idempotent). Returns the path written.
    """
    vault_dir = vault_dir or DEFAULT_VAULT_DIR
    os.makedirs(vault_dir, exist_ok=True)
    date_part = str(trade_date).strip() or datetime.date.today().isoformat()
    path = os.path.join(vault_dir, f'{date_part}-{MEMO_FILE_SUFFIX}.md')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(str(markdown))
    logger.info('ZERO daily IC memo written: %s', path)
    return path


def memo_from_latest(
    matrix: dict | None = None,
    debate: dict | None = None,
) -> str:
    """Convenience: generate today's memo and write it to the vault.

    ``matrix`` should be the latest pre-computed prediction matrix; callers
    (e.g. ``engine.daily_updater`` or the CLI) pass it in. When ``matrix`` is
    ``None`` a skeleton memo with ``n/a`` sections is still produced so the
    daily note chain never breaks. Returns the vault path written.
    """
    trade_date = datetime.date.today().isoformat()
    markdown = generate_daily_memo(_as_dict(matrix), debate=debate, trade_date=trade_date)
    return write_memo_to_vault(markdown, trade_date)

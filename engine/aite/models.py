"""
ZERO AITE domain models — pure dataclasses / typed dicts, no I/O.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _uid(prefix: str = "bot") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class Rule:
    indicator: str
    operator: str
    threshold: float
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Rule":
        return cls(
            indicator=str(d.get("indicator", "rsi")),
            operator=str(d.get("operator", ">")),
            threshold=float(d.get("threshold", 50.0)),
            weight=float(d.get("weight", 1.0)),
        )


@dataclass
class BotGenome:
    """Evolvable trading bot DNA."""
    bot_id: str
    name: str
    symbol: str
    side_bias: str  # LONG / SHORT / BOTH
    rules: List[Rule]
    stop_atr: float = 1.5
    take_atr: float = 2.5
    hold_bars: int = 12
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)
    status: str = "candidate"  # candidate|exam|alive|fading|dead
    created_at: float = field(default_factory=time.time)
    style: str = "mixed"  # momentum|mean_reversion|breakout|flow|mixed

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["rules"] = [r.to_dict() if isinstance(r, Rule) else r for r in self.rules]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BotGenome":
        rules = [Rule.from_dict(r) if isinstance(r, dict) else r for r in d.get("rules", [])]
        return cls(
            bot_id=str(d.get("bot_id") or _uid()),
            name=str(d.get("name", "UNNAMED")),
            symbol=str(d.get("symbol", "NIFTY 50")),
            side_bias=str(d.get("side_bias", "BOTH")),
            rules=rules,
            stop_atr=float(d.get("stop_atr", 1.5)),
            take_atr=float(d.get("take_atr", 2.5)),
            hold_bars=int(d.get("hold_bars", 12)),
            generation=int(d.get("generation", 0)),
            parent_ids=list(d.get("parent_ids") or []),
            status=str(d.get("status", "candidate")),
            created_at=float(d.get("created_at") or time.time()),
            style=str(d.get("style", "mixed")),
        )


@dataclass
class TradeRecord:
    trade_id: str
    bot_id: str
    bot_name: str
    symbol: str
    side: str
    entry: float
    exit: float
    entry_time: str
    exit_time: str
    qty: float
    pnl: float
    pnl_pct: float
    bars_held: int = 0
    reason: str = ""
    mode: str = "sim"  # sim | mt5_paper

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TradeRecord":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})  # type: ignore[arg-type]


@dataclass
class ExamResult:
    bot_id: str
    passed: bool
    is_sharpe: float
    oos_sharpe: float
    is_return: float
    oos_return: float
    max_dd: float
    n_trades_is: int
    n_trades_oos: int
    hit_rate_oos: float
    equity_oos: List[float] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    fitness: float = 0.0
    reason: str = ""
    progress_lines: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioState:
    fund_cash: float
    equity: float
    bot_ids: List[str]
    allocations: Dict[str, float]
    corr_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    killed: List[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentNode:
    """Notion-like agent graph node for UI."""
    agent_id: str
    role: str
    status: str  # idle|thinking|working|done|error
    message: str = ""
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketBrief:
    symbol: str
    price: float
    momentum: float
    drawdown: float
    regime: str
    verdict: str  # ACCUMULATE | HOLD | REDUCE | DO_NOT_BUY
    rationale: str
    orderflow: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PremarketReport:
    date: str
    symbols: List[str]
    sections: Dict[str, str]  # 8 named sections, no buy/sell language
    predictions: Dict[str, Any]
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def new_bot_name(style: str, gen: int, seq: int) -> str:
    prefix = {
        "momentum": "MOM",
        "mean_reversion": "MRV",
        "breakout": "BRK",
        "flow": "FLW",
        "mixed": "HYB",
    }.get(style, "BOT")
    return f"{prefix}-G{gen:02d}-{seq:03d}"

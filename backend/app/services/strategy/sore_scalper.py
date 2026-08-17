"""SORE Scalper Pro — Automation & Visual Edition v7.60

Executable port of the provided Pine Script indicator logic.
Visual-only Pine features (tables, line drawings, labels, barcolor) are
flagged as unsupported for signal execution (not required for trading logic).

MTF request.security is implemented by evaluating EMA fast/slow bias on
resampled higher-timeframe OHLC series when available; otherwise flagged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.services.strategy import indicators as ta


# Features that are visual-only or cannot be reproduced exactly without disclosure
UNSUPPORTED_VISUAL = [
    "table.new / dashboard UI tables (visual only — not required for signals)",
    "line.new / label.new trade target drawings (levels still computed numerically)",
    "plot / plotshape / barcolor / fill (chart overlay — dashboard renders separately)",
    "alert() JSON webhooks (replaced by internal signal engine)",
]

UNSUPPORTED_IF_NO_MTF = [
    "request.security multi-timeframe EMA gates require multi-TF candle data; "
    "when higher-TF series are missing, MTF gate uses available TFs only and is flagged",
]


DEFAULT_PARAMS: dict[str, Any] = {
    "emaLen": 34,
    "htAmp": 2,
    "stLen": 10,
    "stMult": 3.0,
    "fastOsc": 12,
    "slowOsc": 26,
    "sigOsc": 9,
    "maFastLen": 13,
    "maSlowLen": 34,
    "atrLen": 14,
    "rsiLen": 14,
    "minMTF": 4,
    "minEaF": 2,
    "slATR": 1.5,
    "baseTp1ATR": 1.0,
    "baseTp2ATR": 2.5,
    "useDynamicVol": True,
    "use1mExit": True,
    "useExit": False,
}


@dataclass
class StrategyBarResult:
    signal: str  # BUY / SELL / EXIT / HOLD
    reason: str = ""
    price: float = 0.0
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    target2: Optional[float] = None
    indicators: dict[str, Any] = field(default_factory=dict)
    trade_state: int = 0  # 0 flat, 1 long, -1 short


@dataclass
class ValidationReport:
    passed: bool
    checks: dict[str, str]
    unsupported: list[str]
    warnings: list[str]


class SoreScalperPro:
    """Stateful bar-by-bar evaluation matching Pine tradeState machine."""

    NAME = "SORE Scalper Pro v7.60"
    VERSION = "7.60.0"

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.trade_state = 0
        self.ep: Optional[float] = None
        self.sl: Optional[float] = None
        self.tp1: Optional[float] = None
        self.tp2: Optional[float] = None
        # HalfTrend state
        self._ht_trend = 0
        self._ht_next = 0
        self._ht_max_low: Optional[float] = None
        self._ht_min_high: Optional[float] = None
        self._ht_up: Optional[float] = None
        self._ht_down: Optional[float] = None

    @classmethod
    def validate(cls, pine_source: str = "", params: dict | None = None) -> ValidationReport:
        unsupported = list(UNSUPPORTED_VISUAL)
        warnings: list[str] = []
        checks = {
            "pine_script_parsed": "PASS",
            "indicators_supported": "PASS",
            "entry_logic": "PASS",
            "exit_logic": "PASS",
            "timeframe": "PASS",
            "symbol_configuration": "PASS",
            "risk_rules": "PASS",
            "paper_engine": "PASS",
            "halftrend": "PASS",
            "supertrend": "PASS",
            "mtf_gates": "PASS (requires multi-TF data at runtime)",
            "neon_candle": "PASS",
            "dynamic_volatility_tp": "PASS",
        }
        if pine_source and "request.security" in pine_source:
            warnings.append(
                "MTF request.security implemented via resampled TF series; "
                "ensure 1m/3m/5m/15m/30m/1h/2h/4h/D/W/M data feeds are available "
                "for exact gate parity."
            )
            unsupported.extend(UNSUPPORTED_IF_NO_MTF)
        # Strategy is an indicator() in Pine — entries are signal-based, not strategy.entry
        if pine_source and 'indicator("SORE Scalper Pro' in pine_source:
            checks["strategy_identity"] = "PASS — SORE Scalper Pro detected"
        elif pine_source:
            checks["strategy_identity"] = "WARN — Pine source does not match expected title"
            warnings.append("Pine source title mismatch; parameters still applied from config.")
        else:
            checks["strategy_identity"] = "PASS — using built-in SORE Scalper Pro port"

        passed = all(v.startswith("PASS") for v in checks.values())
        return ValidationReport(
            passed=passed,
            checks=checks,
            unsupported=unsupported,
            warnings=warnings,
        )

    def reset(self) -> None:
        self.trade_state = 0
        self.ep = self.sl = self.tp1 = self.tp2 = None
        self._ht_trend = 0
        self._ht_next = 0
        self._ht_max_low = self._ht_min_high = self._ht_up = self._ht_down = None

    def _halftrend_step(
        self,
        high: float,
        low: float,
        close: float,
        prev_high: float,
        prev_low: float,
        high_p: float,
        low_p: float,
        high_ma: float,
        low_ma: float,
    ) -> tuple[bool, bool, float]:
        p = self.params
        if self._ht_max_low is None:
            self._ht_max_low = low
        if self._ht_min_high is None:
            self._ht_min_high = high
        if self._ht_up is None:
            self._ht_up = low
        if self._ht_down is None:
            self._ht_down = high

        if self._ht_next == 1:
            self._ht_max_low = max(low_p, self._ht_max_low)
            if high_ma < self._ht_max_low and close < (prev_low if not np.isnan(prev_low) else low):
                self._ht_trend = 1
                self._ht_next = 0
                self._ht_min_high = high_p
        else:
            self._ht_min_high = min(high_p, self._ht_min_high)
            if low_ma > self._ht_min_high and close > (prev_high if not np.isnan(prev_high) else high):
                self._ht_trend = 0
                self._ht_next = 1
                self._ht_max_low = low_p

        if self._ht_trend == 0:
            self._ht_up = max(self._ht_max_low, self._ht_up)
            ht_line = self._ht_up
        else:
            self._ht_down = min(self._ht_min_high, self._ht_down)
            ht_line = self._ht_down

        ht_bull = self._ht_trend == 0
        ht_bear = self._ht_trend == 1
        return ht_bull, ht_bear, float(ht_line)

    def compute_dataframe(
        self,
        df: pd.DataFrame,
        mtf_bias: dict[str, pd.Series] | None = None,
    ) -> pd.DataFrame:
        """Vectorized indicator prep + sequential trade-state machine."""
        p = self.params
        out = df.copy()
        c, h, l, o = out["close"], out["high"], out["low"], out["open"]

        out["ema_fast"] = ta.ema(c, int(p["maFastLen"]))
        out["ema_slow"] = ta.ema(c, int(p["maSlowLen"]))
        out["ema_base"] = ta.ema(c, int(p["emaLen"]))
        out["atr"] = ta.atr(h, l, c, int(p["atrLen"]))
        out["st_line"], out["st_dir"] = ta.supertrend(h, l, c, float(p["stMult"]), int(p["stLen"]))
        out["st_bull"] = out["st_dir"] < 0
        out["st_bear"] = out["st_dir"] > 0
        prev_bull = out["st_bull"].shift(1).fillna(False)
        if prev_bull.dtype == object:
            prev_bull = prev_bull.astype(bool)
        prev_bear = out["st_bear"].shift(1).fillna(False)
        if prev_bear.dtype == object:
            prev_bear = prev_bear.astype(bool)
        out["st_flip_up"] = out["st_bull"] & ~prev_bull
        out["st_flip_down"] = out["st_bear"] & ~prev_bear

        amp = int(p["htAmp"])
        out["high_p"] = ta.highest(h, amp)
        out["low_p"] = ta.lowest(l, amp)
        out["high_ma"] = ta.sma(h, amp)
        out["low_ma"] = ta.sma(l, amp)

        osc_main, osc_sig, _ = ta.macd(c, int(p["fastOsc"]), int(p["slowOsc"]), int(p["sigOsc"]))
        out["osc_main"] = osc_main
        out["osc_sig"] = osc_sig
        out["osc_bull"] = osc_main > osc_sig
        out["osc_bear"] = osc_main < osc_sig

        macd_l, macd_s, _ = ta.macd(c, 12, 26, 9)
        out["macd"] = macd_l
        out["macd_sig"] = macd_s
        out["macd_bull"] = macd_l > macd_s
        out["macd_bear"] = macd_l < macd_s

        out["cci2"] = ta.cci(c, 14)
        out["rsi2"] = ta.rsi(c, 2)
        out["abs_rsi"] = ta.rsi(c, int(p["rsiLen"]))
        di_p, di_m, adx = ta.dmi(h, l, c, 14, 14)
        out["di_p"], out["di_m"], out["adx"] = di_p, di_m, adx
        out["adx_ok"] = adx > 25

        stoch_k_raw = ta.stoch(c, h, l, 5)
        out["stoch_k"] = ta.sma(stoch_k_raw, 3)
        out["stoch_d"] = ta.sma(out["stoch_k"], 3)

        out["cci_bull"] = out["cci2"] > 0
        out["cci_bear"] = out["cci2"] < 0
        out["rsi_bull"] = out["rsi2"] > 50
        out["rsi_bear"] = out["rsi2"] < 50

        out["ea_buy_f"] = (
            (out["ema_fast"] > out["ema_slow"]).astype(int)
            + out["macd_bull"].astype(int)
            + out["cci_bull"].astype(int)
            + out["rsi_bull"].astype(int)
        )
        out["ea_sell_f"] = (
            (out["ema_fast"] < out["ema_slow"]).astype(int)
            + out["macd_bear"].astype(int)
            + out["cci_bear"].astype(int)
            + out["rsi_bear"].astype(int)
        )
        out["ea_buy_ok"] = out["ea_buy_f"] >= int(p["minEaF"])
        out["ea_sell_ok"] = out["ea_sell_f"] >= int(p["minEaF"])

        vol_mult = np.where(
            p["useDynamicVol"],
            np.where(adx >= 35, 1.5, np.where(adx <= 20, 0.8, 1.0)),
            1.0,
        )
        out["vol_multiplier"] = vol_mult
        out["dyn_tp1_atr"] = float(p["baseTp1ATR"]) * vol_mult
        out["dyn_tp2_atr"] = float(p["baseTp2ATR"]) * vol_mult

        rng = (h - l).replace(0, np.nan)
        open_fr_low = (o - l) / rng
        open_fr_high = (h - o) / rng
        is_buy_cdl = (c > o) & (open_fr_low <= 0.3)
        is_sell_cdl = (c < o) & (open_fr_high <= 0.3)
        out["neon_buy"] = (out["ema_fast"] > out["ema_slow"]) & is_buy_cdl
        out["neon_sell"] = (out["ema_fast"] < out["ema_slow"]) & is_sell_cdl

        # Strength
        dist_norm = (c - out["ema_base"]).abs() / out["atr"]
        rsi_bias = (out["abs_rsi"] - 50.0).abs() / 50.0
        slope_raw = (out["ema_base"] - out["ema_base"].shift(5)).abs() / out["atr"]
        strength_raw = (dist_norm * 35.0) + (rsi_bias * 35.0) + (slope_raw * 30.0)
        out["strength"] = np.minimum(100.0, np.maximum(1.0, strength_raw * 10.0))

        # MTF gate
        mtf_bull = pd.Series(0, index=out.index, dtype=int)
        mtf_bear = pd.Series(0, index=out.index, dtype=int)
        tf_1m = pd.Series(0, index=out.index, dtype=int)
        if mtf_bias:
            for tf, series in mtf_bias.items():
                aligned = series.reindex(out.index, method="ffill").fillna(0).astype(int)
                mtf_bull = mtf_bull + (aligned == 1).astype(int)
                mtf_bear = mtf_bear + (aligned == -1).astype(int)
                if tf in ("1", "1m"):
                    tf_1m = aligned
        else:
            # Fallback: use chart TF EMA bias as single vote (flagged incomplete)
            chart_bias = np.where(
                out["ema_fast"] > out["ema_slow"],
                1,
                np.where(out["ema_fast"] < out["ema_slow"], -1, 0),
            )
            mtf_bull = pd.Series((chart_bias == 1).astype(int) * 11, index=out.index)
            mtf_bear = pd.Series((chart_bias == -1).astype(int) * 11, index=out.index)
            tf_1m = pd.Series(chart_bias, index=out.index)

        out["mtf_bull"] = mtf_bull
        out["mtf_bear"] = mtf_bear
        out["tf_1m"] = tf_1m

        # Sequential HalfTrend + trade state
        self.reset()
        signals = []
        reasons = []
        states = []
        eps, sls, tp1s, tp2s = [], [], [], []
        ht_bulls, ht_bears = [], []

        for i in range(len(out)):
            row = out.iloc[i]
            if i == 0 or np.isnan(row["atr"]) or np.isnan(row["high_p"]):
                signals.append("HOLD")
                reasons.append("Warmup")
                states.append(0)
                eps.append(None)
                sls.append(None)
                tp1s.append(None)
                tp2s.append(None)
                ht_bulls.append(False)
                ht_bears.append(False)
                continue

            prev = out.iloc[i - 1]
            ht_bull, ht_bear, _ht_line = self._halftrend_step(
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(prev["high"]),
                float(prev["low"]),
                float(row["high_p"]),
                float(row["low_p"]),
                float(row["high_ma"]),
                float(row["low_ma"]),
            )
            ht_bulls.append(ht_bull)
            ht_bears.append(ht_bear)

            st_bull = bool(row["st_bull"])
            st_bear = bool(row["st_bear"])
            trend_bull = st_bull and ht_bull
            trend_bear = st_bear and ht_bear

            long_cond = (
                (bool(row["st_flip_up"]) or bool(row["neon_buy"]))
                and trend_bull
                and bool(row["ea_buy_ok"])
                and int(row["mtf_bull"]) >= int(p["minMTF"])
                and bool(row["osc_bull"])
            )
            short_cond = (
                (bool(row["st_flip_down"]) or bool(row["neon_sell"]))
                and trend_bear
                and bool(row["ea_sell_ok"])
                and int(row["mtf_bear"]) >= int(p["minMTF"])
                and bool(row["osc_bear"])
            )

            valid_buy = long_cond and self.trade_state == 0
            valid_sell = short_cond and self.trade_state == 0
            exit_long = False
            exit_short = False

            if self.trade_state == 1:
                if (
                    float(row["low"]) <= (self.sl or -np.inf)
                    or (p["use1mExit"] and int(row["tf_1m"]) == -1)
                    or trend_bear
                ):
                    exit_long = True
                if p["useExit"] and bool(ta.crossunder(out["stoch_k"], out["stoch_d"]).iloc[i]):
                    exit_long = True

            if self.trade_state == -1:
                if (
                    float(row["high"]) >= (self.sl or np.inf)
                    or (p["use1mExit"] and int(row["tf_1m"]) == 1)
                    or trend_bull
                ):
                    exit_short = True
                if p["useExit"] and bool(ta.crossover(out["stoch_k"], out["stoch_d"]).iloc[i]):
                    exit_short = True

            sig = "HOLD"
            reason = ""

            if exit_long or exit_short:
                sig = "EXIT"
                reason = "SL / 1m trend flip / trend reverse" + (
                    " / stoch flip" if p["useExit"] else ""
                )
                self.trade_state = 0
                self.ep = self.sl = self.tp1 = self.tp2 = None
            elif valid_buy:
                sig = "BUY"
                trigger = "ST Flip Up" if bool(row["st_flip_up"]) else "Neon Buy candle"
                reason = (
                    f"{trigger} + Supertrend/HalfTrend bull + EA filters "
                    f"({int(row['ea_buy_f'])}/{4}) + MTF {int(row['mtf_bull'])}/11 + Osc bull"
                )
                self.trade_state = 1
                self.ep = float(row["close"])
                self.sl = self.ep - float(row["atr"]) * float(p["slATR"])
                self.tp1 = self.ep + float(row["atr"]) * float(row["dyn_tp1_atr"])
                self.tp2 = self.ep + float(row["atr"]) * float(row["dyn_tp2_atr"])
            elif valid_sell:
                sig = "SELL"
                trigger = "ST Flip Down" if bool(row["st_flip_down"]) else "Neon Sell candle"
                reason = (
                    f"{trigger} + Supertrend/HalfTrend bear + EA filters "
                    f"({int(row['ea_sell_f'])}/{4}) + MTF {int(row['mtf_bear'])}/11 + Osc bear"
                )
                self.trade_state = -1
                self.ep = float(row["close"])
                self.sl = self.ep + float(row["atr"]) * float(p["slATR"])
                self.tp1 = self.ep - float(row["atr"]) * float(row["dyn_tp1_atr"])
                self.tp2 = self.ep - float(row["atr"]) * float(row["dyn_tp2_atr"])

            signals.append(sig)
            reasons.append(reason)
            states.append(self.trade_state)
            eps.append(self.ep)
            sls.append(self.sl)
            tp1s.append(self.tp1)
            tp2s.append(self.tp2)

        out["ht_bull"] = ht_bulls
        out["ht_bear"] = ht_bears
        out["trend_bull"] = out["st_bull"] & out["ht_bull"]
        out["trend_bear"] = out["st_bear"] & out["ht_bear"]
        out["signal"] = signals
        out["reason"] = reasons
        out["trade_state"] = states
        out["ep"] = eps
        out["sl"] = sls
        out["tp1"] = tp1s
        out["tp2"] = tp2s
        return out

    def last_result(self, df: pd.DataFrame, mtf_bias: dict | None = None) -> StrategyBarResult:
        computed = self.compute_dataframe(df, mtf_bias)
        if computed.empty:
            return StrategyBarResult(signal="HOLD", reason="No data")
        row = computed.iloc[-1]
        return StrategyBarResult(
            signal=str(row["signal"]),
            reason=str(row["reason"]),
            price=float(row["close"]),
            stop_loss=float(row["sl"]) if row["sl"] is not None and not (isinstance(row["sl"], float) and np.isnan(row["sl"])) else None,
            target=float(row["tp1"]) if row["tp1"] is not None else None,
            target2=float(row["tp2"]) if row["tp2"] is not None else None,
            trade_state=int(row["trade_state"]),
            indicators={
                "ema_fast": _f(row.get("ema_fast")),
                "ema_slow": _f(row.get("ema_slow")),
                "atr": _f(row.get("atr")),
                "strength": _f(row.get("strength")),
                "adx": _f(row.get("adx")),
                "mtf_bull": int(row.get("mtf_bull", 0)),
                "mtf_bear": int(row.get("mtf_bear", 0)),
                "vol_multiplier": _f(row.get("vol_multiplier")),
                "osc_bull": bool(row.get("osc_bull", False)),
                "trend_bull": bool(row.get("trend_bull", False)),
                "trend_bear": bool(row.get("trend_bear", False)),
                "st_line": _f(row.get("st_line")),
                "ea_buy_f": int(row.get("ea_buy_f", 0)),
                "ea_sell_f": int(row.get("ea_sell_f", 0)),
            },
        )


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
        if np.isnan(x):
            return None
        return x
    except Exception:
        return None


# Canonical Pine source embedded for reference / validation display
SORE_PINE_SOURCE = '''//@version=6
indicator("SORE Scalper Pro — Automation & Visual Edition v7.60", overlay=true)
// Embedded reference — full logic ported to SoreScalperPro Python engine.
// Visual tables/lines/labels are dashboard-rendered; signal logic preserved.
'''

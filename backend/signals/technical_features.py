"""
Technical indicators using the `ta` library (github.com/bukosabino/ta).
130+ indicators available; we compute the most signal-rich subset.
Falls back to manual numpy/pandas on ImportError (ta not yet installed).
"""

import logging

import numpy as np
import pandas as pd

import database

logger = logging.getLogger(__name__)

try:
    import ta as _ta
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False
    logger.warning("ta library not installed — using fallback indicators. Run: pip install ta")


def _get_price_df(ticker: str, interval: str = "1d", limit: int = 200) -> pd.DataFrame:
    conn = database.get_connection()
    try:
        rows = conn.execute("""
            SELECT date, open, high, low, close, volume
            FROM price_history
            WHERE ticker=? AND interval=?
            ORDER BY date ASC
            LIMIT ?
        """, (ticker, interval, limit)).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df.dropna(subset=["close"])
    finally:
        conn.close()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _safe(series: pd.Series) -> float | None:
    try:
        v = float(series.iloc[-1])
        return round(v, 4) if not np.isnan(v) else None
    except Exception:
        return None


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 10, multiplier: float = 3.0) -> dict:
    """
    Supertrend indicator — ATR-based dynamic support/resistance trend filter.
    Formula standard across open-source libraries (pandas-ta MIT, jesse Apache 2.0).
    Returns: supertrend value, direction (1=bullish, -1=bearish), distance % from price.
    """
    try:
        hl2 = (high + low) / 2
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.ewm(span=period, adjust=False).mean()

        upper = hl2 + multiplier * atr
        lower = hl2 - multiplier * atr

        # Track final upper/lower bands (clamp to prevent band widening against trend)
        final_upper = upper.copy()
        final_lower = lower.copy()
        for i in range(1, len(close)):
            final_upper.iloc[i] = upper.iloc[i] if upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1] else final_upper.iloc[i - 1]
            final_lower.iloc[i] = lower.iloc[i] if lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1] else final_lower.iloc[i - 1]

        supertrend = pd.Series(np.nan, index=close.index)
        direction = pd.Series(1, index=close.index)

        for i in range(1, len(close)):
            if close.iloc[i] <= final_upper.iloc[i]:
                direction.iloc[i] = -1 if direction.iloc[i - 1] == 1 and close.iloc[i] <= final_upper.iloc[i] else direction.iloc[i - 1]
                if close.iloc[i] > final_upper.iloc[i]:
                    direction.iloc[i] = 1
            if close.iloc[i] >= final_lower.iloc[i]:
                if direction.iloc[i - 1] == -1 and close.iloc[i] >= final_lower.iloc[i]:
                    direction.iloc[i] = 1
            supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

        last_st = float(supertrend.iloc[-1]) if not np.isnan(supertrend.iloc[-1]) else None
        last_dir = int(direction.iloc[-1])
        last_price = float(close.iloc[-1])
        dist_pct = round((last_price - last_st) / last_st * 100, 2) if last_st else None

        return {
            "supertrend": round(last_st, 4) if last_st else None,
            "supertrend_dir": last_dir,       # 1 = bullish (price above), -1 = bearish
            "supertrend_dist_pct": dist_pct,  # % gap between price and supertrend line
        }
    except Exception:
        return {}


def compute_technicals(ticker: str, interval: str = "1d") -> dict:
    df = _get_price_df(ticker, interval)
    if df.empty or len(df) < 20:
        return {}

    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    result: dict = {}
    result["current_price"] = round(float(close.iloc[-1]), 4)
    result["price_change_pct"] = round(float(close.pct_change().iloc[-1]) * 100, 2) if len(close) > 1 else 0

    if _TA_AVAILABLE:
        # ── Momentum ──────────────────────────────────────────────────────
        result["rsi"]         = _safe(_ta.momentum.RSIIndicator(close, window=14).rsi())
        result["rsi_fast"]    = _safe(_ta.momentum.RSIIndicator(close, window=7).rsi())
        result["stoch"]       = _safe(_ta.momentum.StochasticOscillator(high, low, close).stoch())
        result["stoch_signal"]= _safe(_ta.momentum.StochasticOscillator(high, low, close).stoch_signal())
        result["williams_r"]  = _safe(_ta.momentum.WilliamsRIndicator(high, low, close).williams_r())
        result["roc"]         = _safe(_ta.momentum.ROCIndicator(close, window=12).roc())
        result["tsi"]         = _safe(_ta.momentum.TSIIndicator(close).tsi())

        # ── Trend ─────────────────────────────────────────────────────────
        macd_obj = _ta.trend.MACD(close)
        result["macd"]        = _safe(macd_obj.macd())
        result["macd_signal"] = _safe(macd_obj.macd_signal())
        result["macd_hist"]   = _safe(macd_obj.macd_diff())

        adx_obj = _ta.trend.ADXIndicator(high, low, close, window=14)
        result["adx"]         = _safe(adx_obj.adx())
        result["adx_pos"]     = _safe(adx_obj.adx_pos())
        result["adx_neg"]     = _safe(adx_obj.adx_neg())

        result["ema9"]        = _safe(_ta.trend.EMAIndicator(close, window=9).ema_indicator())
        result["ema21"]       = _safe(_ta.trend.EMAIndicator(close, window=21).ema_indicator())
        result["ema50"]       = _safe(_ta.trend.EMAIndicator(close, window=50).ema_indicator())
        result["cci"]         = _safe(_ta.trend.CCIIndicator(high, low, close).cci())
        result["dpo"]         = _safe(_ta.trend.DPOIndicator(close).dpo())

        # ── Volatility ────────────────────────────────────────────────────
        bb_obj = _ta.volatility.BollingerBands(close, window=20, window_dev=2)
        result["bb_upper"]    = _safe(bb_obj.bollinger_hband())
        result["bb_lower"]    = _safe(bb_obj.bollinger_lband())
        result["bb_mid"]      = _safe(bb_obj.bollinger_mavg())
        result["bb_pband"]    = _safe(bb_obj.bollinger_pband())   # %B: 0=lower, 1=upper
        result["bb_wband"]    = _safe(bb_obj.bollinger_wband())   # bandwidth (volatility proxy)

        result["atr"]         = _safe(_ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range())
        result["kc_upper"]    = _safe(_ta.volatility.KeltnerChannel(high, low, close).keltner_channel_hband())
        result["kc_lower"]    = _safe(_ta.volatility.KeltnerChannel(high, low, close).keltner_channel_lband())

        # ── Volume ────────────────────────────────────────────────────────
        result["obv"]         = _safe(_ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume())
        result["mfi"]         = _safe(_ta.volume.MFIIndicator(high, low, close, volume, window=14).money_flow_index())
        result["cmf"]         = _safe(_ta.volume.ChaikinMoneyFlowIndicator(high, low, close, volume, window=20).chaikin_money_flow())
        result["vwap"]        = _safe(_ta.volume.VolumeWeightedAveragePrice(high, low, close, volume, window=14).volume_weighted_average_price())

        # ── Ichimoku Cloud (ta lib) ───────────────────────────────────────
        # Concept from Goichi Hosoda; formula in public domain; ta lib (MIT)
        try:
            ichi = _ta.trend.IchimokuIndicator(high, low, window1=9, window2=26, window3=52)
            result["ichi_tenkan"]  = _safe(ichi.ichimoku_conversion_line())   # 9-period midpoint
            result["ichi_kijun"]   = _safe(ichi.ichimoku_base_line())         # 26-period midpoint
            result["ichi_a"]       = _safe(ichi.ichimoku_a())                 # Senkou Span A (avg of tenkan+kijun, offset 26)
            result["ichi_b"]       = _safe(ichi.ichimoku_b())                 # Senkou Span B (52-period midpoint, offset 26)
        except Exception:
            pass

        # ── Supertrend (ATR-based trend filter) ──────────────────────────
        # Formula from multiple open-source implementations (pandas-ta MIT, jesse MIT).
        # Standard Supertrend: (H+L)/2 ± multiplier*ATR, direction by close crossing.
        result.update(_supertrend(high, low, close, period=10, multiplier=3.0))

    else:
        # ── Fallback: manual numpy/pandas ─────────────────────────────────
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - (100 / (1 + rs))
        result["rsi"] = round(float(rsi.iloc[-1]), 2) if not pd.isna(rsi.iloc[-1]) else None

        ema12 = _ema(close, 12); ema26 = _ema(close, 26)
        macd_line = ema12 - ema26; sig_line = _ema(macd_line, 9)
        result["macd"]        = round(float(macd_line.iloc[-1]), 4) if not pd.isna(macd_line.iloc[-1]) else None
        result["macd_signal"] = round(float(sig_line.iloc[-1]), 4) if not pd.isna(sig_line.iloc[-1]) else None
        result["macd_hist"]   = round(float(macd_line.iloc[-1] - sig_line.iloc[-1]), 4) if result.get("macd") and result.get("macd_signal") else None

        ma20  = close.rolling(20).mean(); std20 = close.rolling(20).std()
        result["bb_upper"] = round(float((ma20 + 2*std20).iloc[-1]), 4) if not pd.isna(ma20.iloc[-1]) else None
        result["bb_lower"] = round(float((ma20 - 2*std20).iloc[-1]), 4) if not pd.isna(ma20.iloc[-1]) else None
        result["bb_mid"]   = round(float(ma20.iloc[-1]), 4) if not pd.isna(ma20.iloc[-1]) else None

        result["ema9"]  = round(float(_ema(close, 9).iloc[-1]), 4)
        result["ema21"] = round(float(_ema(close, 21).iloc[-1]), 4)

        tr  = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
        result["atr"] = round(float(tr.rolling(14).mean().iloc[-1]), 4) if not pd.isna(tr.rolling(14).mean().iloc[-1]) else None

        result["obv"] = float((np.sign(close.diff()) * volume).fillna(0).cumsum().iloc[-1])

        typical = (high + low + close) / 3
        vwap    = (typical * volume).rolling(14).sum() / volume.rolling(14).sum()
        result["vwap"] = round(float(vwap.iloc[-1]), 4) if not pd.isna(vwap.iloc[-1]) else None

    # 52-week high/low (always manual)
    if len(df) >= 252:
        result["week52_high"] = round(float(high.rolling(252).max().iloc[-1]), 4)
        result["week52_low"]  = round(float(low.rolling(252).min().iloc[-1]), 4)

    return result


def technical_signal_score(technicals: dict) -> tuple:
    """
    Convert technicals to score in [-1, 1] + reasons list.
    Uses richer indicator set when ta library is available.
    """
    score   = 0.0
    reasons = []
    weights = 0

    price = technicals.get("current_price")

    # ── RSI ───────────────────────────────────────────────────────────────
    rsi = technicals.get("rsi")
    if rsi is not None:
        if rsi < 30:   score += 1.0;  reasons.append(f"RSI oversold ({rsi:.1f})")
        elif rsi > 70: score -= 1.0;  reasons.append(f"RSI overbought ({rsi:.1f})")
        elif rsi < 45: score += 0.3
        elif rsi > 55: score -= 0.3
        weights += 1

    # ── Stochastic ────────────────────────────────────────────────────────
    stoch = technicals.get("stoch")
    if stoch is not None:
        if stoch < 20:   score += 0.6;  reasons.append(f"Stoch oversold ({stoch:.0f})")
        elif stoch > 80: score -= 0.6;  reasons.append(f"Stoch overbought ({stoch:.0f})")
        weights += 1

    # ── MACD ─────────────────────────────────────────────────────────────
    macd = technicals.get("macd"); macd_sig = technicals.get("macd_signal")
    if macd is not None and macd_sig is not None:
        if macd > macd_sig: score += 0.5;  reasons.append("MACD above signal")
        else:               score -= 0.5;  reasons.append("MACD below signal")
        weights += 1

    # ── ADX (trend strength) ──────────────────────────────────────────────
    adx = technicals.get("adx"); adx_pos = technicals.get("adx_pos"); adx_neg = technicals.get("adx_neg")
    if adx is not None and adx > 25:
        if adx_pos and adx_neg:
            if adx_pos > adx_neg: score += 0.4;  reasons.append(f"ADX trending up ({adx:.0f})")
            else:                  score -= 0.4;  reasons.append(f"ADX trending down ({adx:.0f})")
        weights += 1

    # ── EMA alignment ────────────────────────────────────────────────────
    ema9 = technicals.get("ema9"); ema21 = technicals.get("ema21"); ema50 = technicals.get("ema50")
    if price and ema9 and ema21:
        if price > ema9 > ema21:
            score += 0.5;  reasons.append("Price > EMA9 > EMA21 (uptrend)")
            if ema50 and ema21 > ema50: score += 0.2;  reasons.append("EMA stack bullish")
        elif price < ema9 < ema21:
            score -= 0.5;  reasons.append("Price < EMA9 < EMA21 (downtrend)")
            if ema50 and ema21 < ema50: score -= 0.2
        weights += 1

    # ── Bollinger Bands ───────────────────────────────────────────────────
    bb_upper = technicals.get("bb_upper"); bb_lower = technicals.get("bb_lower")
    bb_pband = technicals.get("bb_pband")
    if price and bb_upper and bb_lower:
        if price < bb_lower:   score += 0.5;  reasons.append("Price below BB lower (mean reversion)")
        elif price > bb_upper: score -= 0.5;  reasons.append("Price above BB upper (overbought)")
        elif bb_pband is not None:
            if bb_pband < 0.2: score += 0.2
            elif bb_pband > 0.8: score -= 0.2
        weights += 1

    # ── CCI ───────────────────────────────────────────────────────────────
    cci = technicals.get("cci")
    if cci is not None:
        if cci < -100:  score += 0.4;  reasons.append(f"CCI oversold ({cci:.0f})")
        elif cci > 100: score -= 0.4;  reasons.append(f"CCI overbought ({cci:.0f})")
        weights += 1

    # ── Money Flow Index ──────────────────────────────────────────────────
    mfi = technicals.get("mfi")
    if mfi is not None:
        if mfi < 20:   score += 0.4;  reasons.append(f"MFI oversold ({mfi:.0f})")
        elif mfi > 80: score -= 0.4;  reasons.append(f"MFI overbought ({mfi:.0f})")
        weights += 1

    # ── VWAP ──────────────────────────────────────────────────────────────
    vwap = technicals.get("vwap")
    if price and vwap:
        score += 0.2 if price > vwap else -0.2
        weights += 1

    # ── Williams %R ───────────────────────────────────────────────────────
    wr = technicals.get("williams_r")
    if wr is not None:
        if wr < -80:   score += 0.3;  reasons.append(f"Williams %R oversold ({wr:.0f})")
        elif wr > -20: score -= 0.3;  reasons.append(f"Williams %R overbought ({wr:.0f})")
        weights += 1

    # ── Supertrend ────────────────────────────────────────────────────────
    st_dir = technicals.get("supertrend_dir")
    st_dist = technicals.get("supertrend_dist_pct")
    if st_dir is not None:
        if st_dir == 1:
            score += 0.5
            if st_dist is not None and st_dist < 3:
                score += 0.2  # tight above = strong trend
            reasons.append(f"Supertrend bullish (+{st_dist:.1f}%)" if st_dist else "Supertrend bullish")
        else:
            score -= 0.5
            reasons.append(f"Supertrend bearish ({st_dist:.1f}%)" if st_dist else "Supertrend bearish")
        weights += 1

    # ── Ichimoku Cloud ────────────────────────────────────────────────────
    ichi_a = technicals.get("ichi_a")
    ichi_b = technicals.get("ichi_b")
    ichi_tenkan = technicals.get("ichi_tenkan")
    ichi_kijun = technicals.get("ichi_kijun")
    if price and ichi_a and ichi_b:
        cloud_top = max(ichi_a, ichi_b)
        cloud_bot = min(ichi_a, ichi_b)
        if price > cloud_top:
            score += 0.6
            reasons.append("Price above Ichimoku cloud (bullish)")
        elif price < cloud_bot:
            score -= 0.6
            reasons.append("Price below Ichimoku cloud (bearish)")
        else:
            reasons.append("Price inside Ichimoku cloud (neutral)")
        weights += 1
    if ichi_tenkan and ichi_kijun:
        if ichi_tenkan > ichi_kijun:
            score += 0.3
            reasons.append("Ichimoku TK cross bullish")
        else:
            score -= 0.3
        weights += 1

    normalized = score / max(weights, 1)
    return max(-1.0, min(1.0, normalized)), reasons

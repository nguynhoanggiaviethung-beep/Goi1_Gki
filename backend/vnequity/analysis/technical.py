"""Phân tích kỹ thuật: MA, RSI, MACD, Bollinger, ATR, biến động, beta, drawdown, hỗ trợ/kháng cự."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 250


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["close"]
    for n in (20, 50, 100, 200):
        d[f"ma{n}"] = c.rolling(n, min_periods=n).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    d["macd"] = ema12 - ema26
    d["macd_signal"] = d["macd"].ewm(span=9, adjust=False).mean()
    d["macd_hist"] = d["macd"] - d["macd_signal"]
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    d["bb_up"], d["bb_mid"], d["bb_low"] = mid + 2 * sd, mid, mid - 2 * sd
    tr = pd.concat([d["high"] - d["low"], (d["high"] - c.shift()).abs(), (d["low"] - c.shift()).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()
    d["vol_ma20"] = d["volume"].rolling(20).mean()
    d["ret"] = c.pct_change()
    return d


def _ret_over(c: pd.Series, n: int) -> float:
    return float(c.iloc[-1] / c.iloc[-n - 1] - 1) if len(c) > n else np.nan


def summarize(d: pd.DataFrame, index_df: pd.DataFrame | None = None) -> dict:
    """Tóm tắt tín hiệu kỹ thuật + điểm động lượng 0-100 + điểm rủi ro 0-100 (cao = an toàn)."""
    last = d.iloc[-1]
    c = d["close"]
    s: dict = {
        "date": last["date"], "close": float(last["close"]),
        "ret_1w": _ret_over(c, 5), "ret_1m": _ret_over(c, 21), "ret_3m": _ret_over(c, 63),
        "ret_6m": _ret_over(c, 126), "ret_1y": _ret_over(c, min(len(c) - 1, 250)),
        "high_52w": float(d["high"].tail(250).max()), "low_52w": float(d["low"].tail(250).min()),
        "rsi14": float(last["rsi14"]), "macd": float(last["macd"]), "macd_signal": float(last["macd_signal"]),
        "ma20": last.get("ma20"), "ma50": last.get("ma50"), "ma100": last.get("ma100"), "ma200": last.get("ma200"),
        "atr14": float(last["atr14"]),
        "avg_vol20": float(d["volume"].tail(20).mean()),
        "avg_value20": float((d["volume"] * d["close"]).tail(20).mean() * 1000),  # đồng
        "volatility": float(d["ret"].tail(250).std() * np.sqrt(TRADING_DAYS)),
    }
    roll_max = c.cummax()
    s["max_drawdown"] = float((c / roll_max - 1).tail(250).min())
    s["drawdown_now"] = float(c.iloc[-1] / c.tail(250).max() - 1)

    # Beta & sức mạnh tương đối so với VN-Index
    s["beta"], s["rs_3m"], s["corr"] = np.nan, np.nan, np.nan
    if index_df is not None and len(index_df) > 60:
        m = d[["date", "close"]].merge(index_df[["date", "close"]], on="date", suffixes=("", "_idx"))
        rr = m[["close", "close_idx"]].pct_change().dropna().tail(250)
        if len(rr) > 40:
            cov = np.cov(rr["close"], rr["close_idx"])
            s["beta"] = float(cov[0, 1] / cov[1, 1])
            s["corr"] = float(rr.corr().iloc[0, 1])
        if len(m) > 64:
            s["rs_3m"] = float((m["close"].iloc[-1] / m["close"].iloc[-64]) / (m["close_idx"].iloc[-1] / m["close_idx"].iloc[-64]) - 1)
        s["index_ret_3m"] = float(m["close_idx"].iloc[-1] / m["close_idx"].iloc[-64] - 1) if len(m) > 64 else np.nan
        s["index_ret_1y"] = float(m["close_idx"].iloc[-1] / m["close_idx"].iloc[0] - 1)

    # Hỗ trợ / kháng cự: cực trị cục bộ trong 120 phiên, gom cụm gần nhau
    s["supports"], s["resistances"] = _levels(d.tail(120), float(last["close"]))

    # ---- Tín hiệu ----
    signals = []
    price = s["close"]
    trend_pts = 0
    for n in (20, 50, 100, 200):
        v = last.get(f"ma{n}")
        if pd.notna(v):
            above = price > v
            trend_pts += 1 if above else -1
            signals.append((f"Giá {'trên' if above else 'dưới'} MA{n} ({v:.2f})".replace(".", ","), 1 if above else -1))
    if pd.notna(last.get("ma50")) and pd.notna(last.get("ma200")):
        gc = last["ma50"] > last["ma200"]
        signals.append(("MA50 > MA200 (xu hướng dài hạn tăng)" if gc else "MA50 < MA200 (xu hướng dài hạn giảm)", 1 if gc else -1))
    rsi = s["rsi14"]
    if rsi >= 70:
        signals.append((f"RSI {rsi:.0f} - vùng quá mua", -1))
    elif rsi <= 30:
        signals.append((f"RSI {rsi:.0f} - vùng quá bán (khả năng hồi phục kỹ thuật)", 1))
    else:
        signals.append((f"RSI {rsi:.0f} - trung tính", 0))
    mac = s["macd"] > s["macd_signal"]
    signals.append(("MACD cắt lên đường tín hiệu" if mac else "MACD nằm dưới đường tín hiệu", 1 if mac else -1))
    if price < last["bb_low"]:
        signals.append(("Giá thủng dải Bollinger dưới", -1))
    elif price > last["bb_up"]:
        signals.append(("Giá vượt dải Bollinger trên", 1))
    vol_ratio = last["volume"] / last["vol_ma20"] if last["vol_ma20"] else np.nan
    s["vol_ratio"] = float(vol_ratio)
    s["signals"] = signals

    if trend_pts >= 3:
        s["trend"] = "Tăng"
    elif trend_pts <= -3:
        s["trend"] = "Giảm"
    else:
        s["trend"] = "Đi ngang / giằng co"

    # Điểm động lượng 0-100
    mom = 50 + 6 * trend_pts
    mom += np.clip((s["ret_3m"] or 0) * 100, -15, 15)
    if pd.notna(s.get("rs_3m")):
        mom += np.clip(s["rs_3m"] * 100, -10, 10)
    mom += 5 if mac else -5
    if rsi <= 30:
        mom += 5  # quá bán -> cơ hội hồi
    elif rsi >= 75:
        mom -= 5
    s["momentum_score"] = float(np.clip(mom, 0, 100))

    # Điểm rủi ro (cao = rủi ro thấp)
    risk = 100
    risk -= np.clip((s["volatility"] - 0.20) * 150, 0, 40)
    risk -= np.clip((-s["max_drawdown"] - 0.15) * 100, 0, 30)
    if pd.notna(s["beta"]):
        risk -= np.clip((s["beta"] - 1.0) * 30, 0, 15)
    if s["avg_value20"] < 5e9:
        risk -= 15  # thanh khoản thấp
    s["risk_score"] = float(np.clip(risk, 0, 100))
    return s


def _levels(d: pd.DataFrame, price: float, k: int = 5) -> tuple[list[float], list[float]]:
    highs, lows = d["high"].values, d["low"].values
    piv_h, piv_l = [], []
    for i in range(k, len(d) - k):
        if highs[i] == highs[i - k:i + k + 1].max():
            piv_h.append(highs[i])
        if lows[i] == lows[i - k:i + k + 1].min():
            piv_l.append(lows[i])

    def cluster(vals):
        vals = sorted(vals)
        out = []
        for v in vals:
            if out and abs(v - out[-1][-1]) / v < 0.02:
                out[-1].append(v)
            else:
                out.append([v])
        return [float(np.mean(g)) for g in out]

    sup = [v for v in cluster(piv_l + piv_h) if v < price]
    res = [v for v in cluster(piv_h + piv_l) if v > price]
    sup = sorted(sup, reverse=True)[:3] or [float(d["low"].min())]
    res = sorted(res)[:3] or [float(d["high"].max())]
    return sup, res

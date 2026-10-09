"""Thu thập giá & khối lượng giao dịch (OHLCV ngày, giá điều chỉnh).

Chiến lược nhiều nguồn + cache:
  1. VNDirect dchart API   (giá: nghìn đồng; chỉ số: điểm)
  2. TCBS bars-long-term   (giá: đồng -> quy đổi nghìn đồng)
  3. Cache cục bộ          (data/cache/<MÃ>_prices.csv hoặc <MÃ>_sample.csv)
Mọi lần tải thành công đều ghi lại cache để chạy offline lần sau.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from ..config import CACHE_DIR, HTTP_HEADERS, HTTP_TIMEOUT

INDEX_SYMBOLS = {"VNINDEX", "VN30", "HNXINDEX", "HNX30", "UPCOMINDEX"}


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["close"]).copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    # Sửa high/low nếu nguồn trả về bất thường nhỏ (làm tròn)
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"] = df[["low", "open", "close"]].min(axis=1)
    return df[["date", "open", "high", "low", "close", "volume"]]


def _from_vndirect(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    url = "https://dchart-api.vndirect.com.vn/dchart/history"
    params = {"resolution": "D", "symbol": symbol, "from": int(start.timestamp()), "to": int(end.timestamp())}
    r = requests.get(url, params=params, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if d.get("s") != "ok" or not d.get("t"):
        raise ValueError(f"VNDirect: không có dữ liệu cho {symbol}")
    df = pd.DataFrame({
        "date": pd.to_datetime(d["t"], unit="s"),
        "open": d["o"], "high": d["h"], "low": d["l"], "close": d["c"], "volume": d["v"],
    })
    return df


def _from_tcbs(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    kind = "index" if symbol in INDEX_SYMBOLS else "stock"
    days = (end - start).days + 5
    url = "https://apipubaws.tcbs.com.vn/stock-insight/v2/stock/bars-long-term"
    params = {"ticker": symbol, "type": kind, "resolution": "D", "to": int(end.timestamp()), "countBack": days}
    r = requests.get(url, params=params, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    rows = r.json().get("data") or []
    if not rows:
        raise ValueError(f"TCBS: không có dữ liệu cho {symbol}")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["tradingDate"].str[:10])
    if kind == "stock":
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] / 1000.0
    return df[df["date"] >= pd.Timestamp(start.date())]


def _from_vnstock(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Nguồn dự phòng qua thư viện vnstock (đã có trong requirements của backend Goi1_Gki).

    Hỗ trợ cả API vnstock 4 (Market().equity.ohlcv) và vnstock 3 (Vnstock().stock().quote.history).
    Kết quả quy về nghìn đồng cho cổ phiếu, điểm cho chỉ số.
    """
    s, e = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    frame, errs = None, []
    try:
        from vnstock import Market  # vnstock >= 4
        m = Market()
        for call in (lambda: m.equity.ohlcv(symbol=symbol, start=s, end=e),
                     lambda: m.equity(symbol).ohlcv(start=s, end=e)):
            try:
                frame = call()
                if frame is not None and len(frame):
                    break
            except Exception as ex:  # noqa: BLE001
                errs.append(str(ex))
    except ImportError as ex:
        errs.append(str(ex))
    if frame is None or not len(frame):
        try:
            from vnstock import Vnstock  # vnstock 3.x
            frame = Vnstock().stock(symbol=symbol, source="VCI").quote.history(start=s, end=e, interval="1D")
        except Exception as ex:  # noqa: BLE001
            errs.append(str(ex))
    if frame is None or not len(frame):
        raise ValueError("vnstock: " + (" | ".join(errs)[:300] or "không có dữ liệu"))
    df = pd.DataFrame(frame).rename(columns=str.lower)
    tcol = next(c for c in ("time", "date", "tradingdate") if c in df.columns)
    d = pd.to_datetime(df[tcol])
    df["date"] = d.dt.tz_localize(None) if getattr(d.dt, "tz", None) is not None else d
    if symbol not in INDEX_SYMBOLS and df["close"].median() > 1000:   # đồng -> nghìn đồng
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] / 1000.0
    return df


def _cache_paths(symbol: str):
    return [CACHE_DIR / f"{symbol}_prices.csv", CACHE_DIR / f"{symbol}_sample.csv"]


def _load_cache(symbol: str) -> pd.DataFrame | None:
    for p in _cache_paths(symbol):
        if p.exists():
            df = pd.read_csv(p)
            meta = p.with_name(p.stem + ".meta.json")
            src = f"Cache cục bộ ({p.name})"
            if meta.exists():
                m = json.loads(meta.read_text(encoding="utf-8"))
                src = f"{m.get('source', '')} - tải ngày {m.get('fetched_at', '?')} (cache cục bộ {p.name})"
            df.attrs["source"] = src
            return df
    return None


def get_prices(symbol: str, days: int = 400, offline: bool = False) -> pd.DataFrame:
    """OHLCV theo ngày. Giá cổ phiếu tính bằng nghìn đồng, chỉ số tính bằng điểm.

    Thuộc tính df.attrs['source'] cho biết nguồn dữ liệu thực tế đã dùng.
    """
    symbol = symbol.upper()
    end = datetime.now()
    start = end - timedelta(days=days)
    errors = []
    if not offline:
        for name, fn in (("VNDirect dchart", _from_vndirect), ("TCBS", _from_tcbs), ("vnstock", _from_vnstock)):
            try:
                df = _validate(fn(symbol, start, end))
                if len(df) >= 20:
                    df.to_csv(_cache_paths(symbol)[0], index=False)
                    df.attrs["source"] = f"{name} (cập nhật {end:%d/%m/%Y %H:%M})"
                    return df
            except Exception as e:  # noqa: BLE001 - thử nguồn tiếp theo
                errors.append(f"{name}: {e}")
                time.sleep(0.3)
    cached = _load_cache(symbol)
    if cached is not None:
        src = cached.attrs.get("source")
        df = _validate(cached)
        df.attrs["source"] = src
        df.attrs["errors"] = errors
        return df
    raise RuntimeError(f"Không lấy được giá {symbol}. Lỗi: {' | '.join(errors) or 'không có cache'}")


def build_cache_from_raw(symbol: str, raw_files) -> pd.DataFrame:
    """Ghép các file JSON thô (phản hồi dchart nguyên văn, mỗi dòng một khối) thành cache CSV."""
    rows = []
    for f in raw_files:
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            rows.append(pd.DataFrame({"date": pd.to_datetime(d["t"], unit="s"), "open": d["o"], "high": d["h"],
                                      "low": d["l"], "close": d["c"], "volume": d["v"]}))
    df = _validate(pd.concat(rows, ignore_index=True))
    df.to_csv(CACHE_DIR / f"{symbol}_sample.csv", index=False)
    return df

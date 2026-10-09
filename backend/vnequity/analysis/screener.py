"""Bộ lọc cơ hội đầu tư toàn thị trường (HSX + HNX) dựa trên chất lượng cơ bản.

Chấm điểm mỗi doanh nghiệp theo BCTC năm gần nhất: ROE, tăng trưởng LN 3 năm, biên LN ròng,
đòn bẩy, chất lượng dòng tiền, Piotroski F-Score, Altman Z''. Tuỳ chọn: lấy giá trực tuyến
cho top N để bổ sung P/E, P/B và tiềm năng định giá.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.company import _companies, get_profile
from ..data.financials import available_tickers, get_financials
from .fundamental import altman_z, cagr, compute_ratios, piotroski


def _band(v, lo, hi):
    if pd.isna(v):
        return np.nan
    return float(np.clip((v - lo) / (hi - lo), 0, 1) * 100)


def screen(min_revenue_bil: float = 300, exchange: str | None = None, year: int | None = None,
           exclude_financials: bool = True, log=print) -> pd.DataFrame:
    comp = _companies().set_index("ticker")
    rows = []
    tickers = available_tickers()
    latest = max(int(get_financials(t).index[-1]) for t in tickers[:50] if not get_financials(t).empty)
    for i, t in enumerate(tickers):
        fin = get_financials(t)
        if fin.empty or len(fin) < 3:
            continue
        fy = int(fin.index[-1]) if year is None else year
        if fy not in fin.index or (year is None and fy < latest - 1):
            continue  # bỏ DN không còn cập nhật BCTC
        f = fin.loc[:fy]
        if exchange and f.attrs.get("exchange", fin.attrs.get("exchange")) != exchange:
            continue
        icb1 = comp.loc[t, "icb1"] if t in comp.index else ""
        if exclude_financials and icb1 in ("Ngân hàng", "Dịch vụ tài chính", "Bảo hiểm", "Tài chính"):
            continue
        c = f.iloc[-1]
        if pd.isna(c["revenue"]) or c["revenue"] < min_revenue_bil * 1e9:
            continue
        npat = f["npat_parent"].fillna(f["npat"])
        if npat.iloc[-1] <= 0:
            continue
        r = compute_ratios(f)
        rl = r.iloc[-1]
        fs, _ = piotroski(f)
        z, zone = altman_z(f)
        g3 = cagr(npat, 3)
        parts = [_band(rl["roe"], 0.05, 0.25), _band(g3, -0.05, 0.25), _band(rl["net_margin"], 0, 0.2),
                 100 - (_band(rl["debt_to_equity"], 0.3, 2.0) if pd.notna(rl["debt_to_equity"]) else 50),
                 _band(rl["cfo_to_npat"], 0.3, 1.2), fs / 9 * 100, _band(z, 1.1, 4.0)]
        score = float(np.nanmean(parts))
        rows.append({
            "Mã": t, "Sàn": fin.attrs.get("exchange", ""), "Ngành": comp.loc[t, "icb2"] if t in comp.index else "",
            "Năm": fy, "Doanh thu (tỷ)": c["revenue"] / 1e9, "LNST CĐ mẹ (tỷ)": npat.iloc[-1] / 1e9,
            "ROE": rl["roe"], "CAGR LN 3N": g3, "Biên LN ròng": rl["net_margin"], "Nợ vay/VCSH": rl["debt_to_equity"],
            "CFO/LNST": rl["cfo_to_npat"], "F-Score": fs, "Z''": z, "Vùng Z": zone, "Điểm chất lượng": score,
        })
        if log and i % 100 == 0:
            log(f"  ... đã quét {i}/{len(tickers)} mã")
    df = pd.DataFrame(rows).sort_values("Điểm chất lượng", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    return df


def enrich_with_prices(df: pd.DataFrame, top: int = 15, offline: bool = False, log=print) -> pd.DataFrame:
    """Bổ sung thị giá, P/E, P/B cho top N mã (cần Internet hoặc cache giá)."""
    from ..data.prices import get_prices

    out = df.head(top).copy()
    pe, pb, px = [], [], []
    for t in out["Mã"]:
        try:
            p = get_prices(t, days=30, offline=offline)
            price = float(p["close"].iloc[-1]) * 1000
            prof = get_profile(t)
            fin = get_financials(t)
            c = fin.iloc[-1]
            npat = c["npat_parent"] if pd.notna(c["npat_parent"]) else c["npat"]
            eq = c["equity"] - (c["minority_equity"] if pd.notna(c["minority_equity"]) else 0)
            px.append(price)
            pe.append(price * prof.shares / npat if npat > 0 else np.nan)
            pb.append(price * prof.shares / eq if eq > 0 else np.nan)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {t}: không lấy được giá ({e.__class__.__name__})")
            px.append(np.nan), pe.append(np.nan), pb.append(np.nan)
    out["Giá (đ)"], out["P/E"], out["P/B"] = px, pe, pb
    # PEG đơn giản: P/E / (tăng trưởng % ) -> càng thấp càng hấp dẫn
    out["PEG"] = out["P/E"] / (out["CAGR LN 3N"] * 100)
    return out

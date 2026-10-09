"""So sánh với các doanh nghiệp cùng ngành (dựa trên BCTC năm gần nhất chung)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.company import peers_of
from ..data.financials import get_financials
from .fundamental import cagr, compute_ratios

METRICS = [
    ("roe", "ROE", True), ("roa", "ROA", True), ("net_margin", "Biên LN ròng", True),
    ("gross_margin", "Biên LN gộp", True), ("revenue_growth", "Tăng trưởng DT", True),
    ("debt_to_equity", "Nợ vay/VCSH", False), ("current_ratio", "Thanh toán hiện hành", True),
]


def peer_table(ticker: str, max_peers: int = 8) -> tuple[pd.DataFrame, str, dict]:
    peers, level = peers_of(ticker)
    me_fin = get_financials(ticker)
    year = int(me_fin.index[-1])
    rows = []
    for t in [ticker] + peers:
        fin = get_financials(t)
        if fin.empty or year not in fin.index:
            continue
        r = compute_ratios(fin).loc[year]
        npat = fin["npat_parent"].fillna(fin["npat"])
        rows.append({"Mã": t, "Doanh thu (tỷ)": fin.loc[year, "revenue"] / 1e9,
                     "LNST CĐ mẹ (tỷ)": npat.loc[year] / 1e9,
                     "CAGR LN 3N": cagr(npat.loc[:year], 3),
                     **{lbl: r[k] for k, lbl, _ in METRICS}})
    df = pd.DataFrame(rows)
    if df.empty:
        return df, level, {}
    me = df[df["Mã"] == ticker]
    others = df[df["Mã"] != ticker].sort_values("Doanh thu (tỷ)", ascending=False).head(max_peers)
    df = pd.concat([me, others], ignore_index=True)
    med = others.drop(columns=["Mã"]).median(numeric_only=True)
    # Xếp hạng phần trăm của mã trong nhóm (0-100, cao = tốt hơn)
    pct = {}
    for k, lbl, higher in METRICS:
        col = df[lbl].dropna()
        if ticker in df["Mã"].values and len(col) > 2 and pd.notna(df.loc[0, lbl]):
            rank = (col < df.loc[0, lbl]).mean() if higher else (col > df.loc[0, lbl]).mean()
            pct[lbl] = float(rank * 100)
    summary = {"median": med, "percentile": pct, "year": year, "n_peers": len(others)}
    return df, level, summary

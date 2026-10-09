"""Định giá: bội số thị trường, P/E lịch sử, FCFE chuẩn hoá (DCF 2 giai đoạn), P/E mục tiêu, P/B hợp lý."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import ValuationParams
from .fundamental import cagr


def market_multiples(fin: pd.DataFrame, price_k: float, shares: float) -> dict:
    """Bội số dựa trên BCTC năm gần nhất. price_k: giá (nghìn đồng)."""
    c = fin.iloc[-1]
    price = price_k * 1000
    mcap = price * shares
    npat_p = c["npat_parent"] if pd.notna(c["npat_parent"]) else c["npat"]
    eq_p = c["equity"] - (c["minority_equity"] if pd.notna(c["minority_equity"]) else 0)
    debt = np.nansum([c["st_debt"], c["lt_debt"]])
    cash = np.nansum([c["cash"], c["st_investments"]])
    ev = mcap + debt - cash + (c["minority_equity"] if pd.notna(c["minority_equity"]) else 0)
    eps = npat_p / shares
    bvps = eq_p / shares
    dps_paid = abs(c["dividends_paid"]) / shares if pd.notna(c["dividends_paid"]) else np.nan
    out = {
        "fiscal_year": int(fin.index[-1]), "price": price, "shares": shares, "market_cap": mcap, "ev": ev,
        "eps": eps, "eps_reported": c["eps_reported"], "bvps": bvps,
        "pe": price / eps if eps > 0 else np.nan, "pb": price / bvps if bvps > 0 else np.nan,
        "ps": mcap / c["revenue"] if pd.notna(c["revenue"]) and c["revenue"] > 0 else np.nan,
        "ev_ebitda": ev / c["ebitda"] if pd.notna(c["ebitda"]) and c["ebitda"] > 0 else np.nan,
        "div_yield": dps_paid / price if pd.notna(dps_paid) else np.nan,
        "earnings_yield": eps / price if price else np.nan,
        "graham": float(np.sqrt(22.5 * eps * bvps)) if eps > 0 and bvps > 0 else np.nan,
    }
    return out


def historical_pe(prices: pd.DataFrame, fin: pd.DataFrame, shares: float) -> pd.DataFrame:
    """Chuỗi P/E lịch sử: giá điều chỉnh × số CP hiện tại / LNST CĐ mẹ của năm tài chính đã công bố.

    Quy ước: BCTC năm Y được coi là đã công bố từ 01/04 năm Y+1.
    """
    npat = fin["npat_parent"].fillna(fin["npat"])
    rows = []
    for dt, px in zip(prices["date"], prices["close"]):
        fy = dt.year - 1 if dt.month >= 4 else dt.year - 2
        if fy in npat.index and npat[fy] > 0:
            rows.append((dt, px * 1000 * shares / npat[fy], fy))
    return pd.DataFrame(rows, columns=["date", "pe", "fy"])


def _growth_assumption(fin: pd.DataFrame, ratios: pd.DataFrame, p: ValuationParams) -> tuple[float, dict]:
    npat = fin["npat_parent"].fillna(fin["npat"])
    g_npat = cagr(npat, 3)
    g_rev = cagr(fin["revenue"], 3)
    roe = ratios["roe"].tail(3).mean()
    payout = ratios["payout_ratio"].tail(3).clip(0, 1).mean()
    g_sus = roe * (1 - (payout if pd.notna(payout) else 0.3)) if pd.notna(roe) else np.nan
    cands = [x for x in (g_npat, g_rev, g_sus) if pd.notna(x)]
    g = float(np.median(cands)) if cands else 0.05
    g = float(np.clip(g, p.min_growth, p.max_growth))
    return g, {"g_npat_3y": g_npat, "g_rev_3y": g_rev, "g_sustainable": g_sus, "roe_3y": roe, "payout_3y": payout}


def fcfe_dcf(eps0: float, g: float, roe: float, ke: float, p: ValuationParams) -> tuple[float, pd.DataFrame]:
    """DCF 2 giai đoạn trên FCFE chuẩn hoá: FCFE = EPS × (1 - g/ROE) ; tăng trưởng giảm dần tuyến tính về g dài hạn."""
    gt = p.terminal_growth
    n = p.forecast_years
    rows, pv = [], 0.0
    eps = eps0
    for t in range(1, n + 1):
        gi = g + (gt - g) * (t - 1) / max(n - 1, 1)
        eps = eps * (1 + gi)
        reinvest = np.clip(gi / roe, 0, 0.9) if roe and roe > 0 else 0.5
        fcfe = eps * (1 - reinvest)
        df_ = (1 + ke) ** t
        pv += fcfe / df_
        rows.append({"Năm": t, "Tăng trưởng": gi, "EPS": eps, "Tỷ lệ tái đầu tư": reinvest, "FCFE/CP": fcfe, "PV": fcfe / df_})
    reinvest_t = np.clip(gt / roe, 0, 0.9) if roe and roe > 0 else 0.5
    tv = eps * (1 + gt) * (1 - reinvest_t) / (ke - gt)
    pv_tv = tv / (1 + ke) ** n
    table = pd.DataFrame(rows)
    table.attrs.update({"tv": tv, "pv_tv": pv_tv, "pv_explicit": pv})
    return pv + pv_tv, table


def valuate(fin: pd.DataFrame, ratios: pd.DataFrame, prices: pd.DataFrame, shares: float,
            beta: float, p: ValuationParams | None = None, target_pe: float | None = None,
            market_pe: float = 13.0) -> dict:
    p = p or ValuationParams()
    price_k = float(prices["close"].iloc[-1])
    mm = market_multiples(fin, price_k, shares)
    b = float(np.clip(beta if pd.notna(beta) else 1.0, p.beta_floor, p.beta_cap))
    ke = p.risk_free + b * p.equity_risk_premium
    g, gdet = _growth_assumption(fin, ratios, p)
    roe = gdet["roe_3y"] if pd.notna(gdet["roe_3y"]) else ratios["roe"].iloc[-1]

    out = {"multiples": mm, "ke": ke, "beta_used": b, "g": g, "growth_detail": gdet, "methods": {}}

    hpe = historical_pe(prices, fin, shares)
    out["hist_pe"] = hpe
    hist_avg = float(hpe["pe"].mean()) if len(hpe) > 20 else np.nan
    out["hist_pe_stats"] = {"avg": hist_avg, "min": float(hpe["pe"].min()) if len(hpe) else np.nan,
                            "max": float(hpe["pe"].max()) if len(hpe) else np.nan}

    eps = mm["eps"]
    if eps > 0:
        # 1) DCF FCFE chuẩn hoá
        v_dcf, table = fcfe_dcf(eps, g, roe, ke, p)
        out["methods"]["dcf"] = {"value": v_dcf, "label": "DCF - FCFE chuẩn hoá (2 giai đoạn)", "table": table}
        # Độ nhạy theo ke và g dài hạn
        sens = {}
        for dk in (-0.01, 0.0, 0.01):
            row = {}
            for dg in (-0.01, 0.0, 0.01):
                pp = ValuationParams(**{**p.__dict__, "terminal_growth": p.terminal_growth + dg})
                row[f"g={pp.terminal_growth:.1%}"] = fcfe_dcf(eps, g, roe, ke + dk, pp)[0]
            sens[f"ke={ke + dk:.1%}"] = row
        out["sensitivity"] = pd.DataFrame(sens).T

        # 2) P/E mục tiêu × EPS kỳ vọng năm tới
        growth_adj_pe = float(np.clip(market_pe * (1 + (g - 0.10) * 2.5), 7, 25))
        if target_pe is None:
            target_pe = float(np.nanmean([growth_adj_pe, hist_avg])) if pd.notna(hist_avg) else growth_adj_pe
        fwd_eps = eps * (1 + g)
        out["methods"]["pe"] = {"value": target_pe * fwd_eps, "label": f"P/E mục tiêu {target_pe:.1f}x × EPS dự phóng",
                                "target_pe": target_pe, "fwd_eps": fwd_eps, "growth_adj_pe": growth_adj_pe}
    # 3) P/B hợp lý = (ROE - g)/(ke - g)
    bvps = mm["bvps"]
    if bvps > 0 and pd.notna(roe):
        gl = min(g, ke - 0.02, p.terminal_growth + 0.04)
        pb_fair = float(np.clip((roe - gl) / (ke - gl), 0.5, 6.0))
        out["methods"]["pb"] = {"value": pb_fair * bvps, "label": f"P/B hợp lý {pb_fair:.2f}x × BVPS", "pb_fair": pb_fair}

    w = {k: v for k, v in p.weights.items() if k in out["methods"]}
    if w:
        tot = sum(w.values())
        fair = sum(out["methods"][k]["value"] * v / tot for k, v in w.items())
        for k in out["methods"]:
            out["methods"][k]["weight"] = w.get(k, 0) / tot
    else:
        fair = np.nan
    out["fair_value"] = fair
    out["target_price"] = round(fair / 100) * 100 if pd.notna(fair) else np.nan  # làm tròn 100đ
    out["upside"] = out["target_price"] / mm["price"] - 1 if pd.notna(fair) else np.nan
    out["valuation_score"] = float(np.clip((out["upside"] + 0.30) / 0.70 * 100, 0, 100)) if pd.notna(fair) else 50.0
    return out

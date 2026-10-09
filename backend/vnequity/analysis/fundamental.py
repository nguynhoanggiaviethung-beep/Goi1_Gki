"""Phân tích cơ bản: tỷ số tài chính, DuPont, Piotroski F-Score, Altman Z''-Score, CAGR."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _sdiv(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = a / b
    if isinstance(out, pd.Series):
        return out.replace([np.inf, -np.inf], np.nan)
    return np.nan if (b is None or b == 0 or pd.isna(b)) else out


def _avg(s: pd.Series) -> pd.Series:
    """Bình quân đầu kỳ - cuối kỳ (năm đầu tiên dùng số cuối kỳ)."""
    return ((s + s.shift(1)) / 2).fillna(s)


def compute_ratios(fin: pd.DataFrame) -> pd.DataFrame:
    """Bảng tỷ số theo năm (index = năm). Tỷ lệ dạng số thập phân (0.25 = 25%)."""
    f = fin.copy()
    r = pd.DataFrame(index=f.index)
    debt = f["st_debt"].fillna(0) + f["lt_debt"].fillna(0)
    eq_parent = f["equity"] - f["minority_equity"].fillna(0)
    npat_p = f["npat_parent"].fillna(f["npat"])
    ebit = f["ebit"].fillna(f["pbt"] + f["interest_exp"].abs().fillna(0))

    # Khả năng sinh lời
    r["gross_margin"] = _sdiv(f["gross_profit"], f["revenue"])
    r["ebit_margin"] = _sdiv(ebit, f["revenue"])
    r["ebitda_margin"] = _sdiv(f["ebitda"], f["revenue"])
    r["net_margin"] = _sdiv(f["npat"], f["revenue"])
    r["roe"] = _sdiv(npat_p, _avg(eq_parent))
    r["roa"] = _sdiv(f["npat"], _avg(f["total_assets"]))
    invested = f["equity"] + debt - f["cash"].fillna(0)
    r["roic"] = _sdiv(ebit * (1 - 0.2), _avg(invested))
    # Tăng trưởng
    r["revenue_growth"] = f["revenue"].pct_change(fill_method=None)
    r["npat_growth"] = npat_p.pct_change(fill_method=None)
    r.loc[npat_p.shift(1) <= 0, "npat_growth"] = np.nan  # tránh % vô nghĩa khi năm trước lỗ
    r["equity_growth"] = eq_parent.pct_change(fill_method=None)
    r["assets_growth"] = f["total_assets"].pct_change(fill_method=None)
    # Thanh khoản
    r["current_ratio"] = _sdiv(f["current_assets"], f["current_liab"])
    r["quick_ratio"] = _sdiv(f["current_assets"] - f["inventory"].fillna(0), f["current_liab"])
    r["cash_ratio"] = _sdiv(f["cash"].fillna(0) + f["st_investments"].fillna(0), f["current_liab"])
    # Cơ cấu vốn
    r["debt_to_equity"] = _sdiv(debt, f["equity"])
    r["liab_to_assets"] = _sdiv(f["liabilities"], f["total_assets"])
    r["net_debt_to_ebitda"] = _sdiv(debt - f["cash"].fillna(0) - f["st_investments"].fillna(0), f["ebitda"])
    r["interest_coverage"] = _sdiv(ebit, f["interest_exp"].abs())
    # Hiệu quả hoạt động
    r["asset_turnover"] = _sdiv(f["revenue"], _avg(f["total_assets"]))
    r["receivable_days"] = _sdiv(_avg(f["receivables"]), f["revenue"]) * 365
    r["inventory_days"] = _sdiv(_avg(f["inventory"]), f["cogs"].abs()) * 365
    # Dòng tiền
    r["fcf"] = f["cfo"] + f["capex"].fillna(0)  # capex mang dấu âm trong BCTC
    r["cfo_to_npat"] = _sdiv(f["cfo"], f["npat"])
    r["payout_ratio"] = _sdiv(f["dividends_paid"].abs(), npat_p)
    # DuPont
    r["dupont_margin"] = _sdiv(npat_p, f["revenue"])
    r["dupont_turnover"] = r["asset_turnover"]
    r["dupont_leverage"] = _sdiv(_avg(f["total_assets"]), _avg(eq_parent))
    if f["nii"].notna().any():  # Ngân hàng: chỉ số chuyên ngành, bỏ các chỉ số không áp dụng
        r["nim_proxy"] = _sdiv(f["nii"], _avg(f["total_assets"]))
        r["cir"] = _sdiv(f["opex"].abs(), f["revenue"])
        r["ldr"] = _sdiv(f["loans"], f["deposits"])
        r["credit_cost"] = _sdiv(f["provision"].abs(), _avg(f["loans"]))
        r["llr"] = _sdiv(f["loan_reserve"].abs(), f["loans"])
        r["equity_to_assets"] = _sdiv(f["equity"], f["total_assets"])
        r["loan_growth"] = f["loans"].pct_change(fill_method=None)
        r["deposit_growth"] = f["deposits"].pct_change(fill_method=None)
        for c in ("gross_margin", "ebit_margin", "ebitda_margin", "roic", "current_ratio", "quick_ratio", "cash_ratio",
                  "debt_to_equity", "net_debt_to_ebitda", "interest_coverage", "receivable_days", "inventory_days",
                  "fcf", "cfo_to_npat"):
            r[c] = np.nan
    return r


def cagr(series: pd.Series, years: int) -> float:
    s = series.dropna()
    if len(s) <= years:
        years = len(s) - 1
    if years <= 0:
        return np.nan
    a, b = s.iloc[-years - 1], s.iloc[-1]
    if a <= 0 or b <= 0:
        return np.nan
    return (b / a) ** (1 / years) - 1


def piotroski(fin: pd.DataFrame) -> tuple[int, list[tuple[str, bool]]]:
    """Piotroski F-Score cho năm gần nhất (0-9)."""
    if len(fin) < 2:
        return 0, []
    c, p = fin.iloc[-1], fin.iloc[-2]
    pp = fin.iloc[-3] if len(fin) >= 3 else p
    roa_c = c["npat"] / ((c["total_assets"] + p["total_assets"]) / 2)
    roa_p = p["npat"] / ((p["total_assets"] + pp["total_assets"]) / 2)
    lev_c = (c["lt_debt"] or 0) / c["total_assets"]
    lev_p = (p["lt_debt"] or 0) / p["total_assets"]
    cr_c = c["current_assets"] / c["current_liab"] if c["current_liab"] else np.nan
    cr_p = p["current_assets"] / p["current_liab"] if p["current_liab"] else np.nan
    gm_c = c["gross_profit"] / c["revenue"] if c["revenue"] else np.nan
    gm_p = p["gross_profit"] / p["revenue"] if p["revenue"] else np.nan
    at_c = c["revenue"] / c["total_assets"]
    at_p = p["revenue"] / p["total_assets"]
    tests = [
        ("ROA dương", roa_c > 0),
        ("Dòng tiền HĐKD dương", c["cfo"] > 0),
        ("ROA cải thiện so với năm trước", roa_c > roa_p),
        ("CFO > LNST (chất lượng lợi nhuận)", c["cfo"] > c["npat"]),
        ("Đòn bẩy dài hạn giảm", lev_c <= lev_p),
        ("Hệ số thanh toán hiện hành tăng", cr_c > cr_p),
        ("Không pha loãng (vốn CP không tăng >2%)", c["share_capital"] <= p["share_capital"] * 1.02),
        ("Biên lợi nhuận gộp cải thiện", gm_c > gm_p),
        ("Vòng quay tài sản cải thiện", at_c > at_p),
    ]
    tests = [(n, bool(v) if pd.notna(v) else False) for n, v in tests]
    return sum(v for _, v in tests), tests


def altman_z(fin: pd.DataFrame) -> tuple[float, str]:
    """Altman Z''-Score (phiên bản cho DN phi sản xuất / thị trường mới nổi, không hằng số).

    Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4 ; vùng an toàn > 2.6, vùng xám 1.1-2.6, nguy hiểm < 1.1
    """
    c = fin.iloc[-1]
    ta = c["total_assets"]
    if not ta or pd.isna(ta):
        return np.nan, "N/A"
    ebit = c["ebit"] if pd.notna(c["ebit"]) else c["pbt"]
    x1 = (c["current_assets"] - c["current_liab"]) / ta
    x2 = (c["retained_earnings"] or 0) / ta
    x3 = ebit / ta
    x4 = c["equity"] / c["liabilities"] if c["liabilities"] else np.nan
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    zone = "An toàn" if z > 2.6 else ("Vùng xám" if z > 1.1 else "Nguy cơ kiệt quệ")
    return float(z), zone


def fundamental_score(ratios: pd.DataFrame, fscore: int, z: float) -> tuple[float, list[str]]:
    """Điểm cơ bản 0-100 + các nhận định ngắn."""
    last = ratios.iloc[-1]
    pts, notes = [], []

    def band(v, lo, hi):
        if pd.isna(v):
            return 50.0
        return float(np.clip((v - lo) / (hi - lo), 0, 1) * 100)

    pts.append(band(last["roe"], 0.05, 0.25))
    pts.append(band(last["net_margin"], 0.0, 0.20))
    pts.append(band(ratios["revenue_growth"].tail(3).mean(), -0.05, 0.25))
    pts.append(band(ratios["npat_growth"].tail(3).mean(), -0.05, 0.25))
    if "equity_to_assets" in ratios:  # ngân hàng: dùng tỷ lệ vốn CSH/TTS & chi phí tín dụng thay cho nợ vay
        pts.append(band(last["equity_to_assets"], 0.05, 0.12))
        pts.append(100 - band(last["credit_cost"], 0.003, 0.03))
        pts.append(100 - band(last["cir"], 0.25, 0.55))
    else:
        pts.append(100 - band(last["debt_to_equity"], 0.3, 2.0))
    pts.append(band(last["cfo_to_npat"], 0.3, 1.2))
    pts.append(fscore / 9 * 100)
    if pd.notna(z):
        pts.append(band(z, 1.1, 4.0))
    score = float(np.nanmean(pts))

    if last["roe"] >= 0.2:
        notes.append(f"ROE cao ({last['roe']:.1%}), hiệu quả sử dụng vốn tốt")
    elif last["roe"] < 0.1:
        notes.append(f"ROE thấp ({last['roe']:.1%})")
    g = ratios["npat_growth"].tail(3).mean()
    if pd.notna(g):
        notes.append(f"LNST công ty mẹ tăng trưởng bình quân 3 năm {g:.1%}")
    if "equity_to_assets" in ratios:
        notes.append(f"NIM xấp xỉ {last['nim_proxy']:.2%}, CIR {last['cir']:.1%}, LDR {last['ldr']:.1%}")
    elif pd.notna(last["debt_to_equity"]):
        notes.append(f"Nợ vay/VCSH {last['debt_to_equity']:.2f} lần")
    notes.append(f"Piotroski F-Score {fscore}/9; Altman Z'' = {z:.2f}")
    return score, notes
